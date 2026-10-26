"""受限的 Agent SQL 执行器。

这里只接受 Agent 生成的参数化 SQL。SQL 校验在数据库执行之前完成，所有
statement 使用同一条 MySQL 连接和事务。请求幂等缓存是进程内的；数据库层的
``todos.request_id`` 唯一约束作为持久化兜底。
"""

from __future__ import annotations

import re
import logging
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from threading import RLock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlglot
from sqlglot import exp

import db
from availability import query_metadata, occupancy_statements
from reminder_sql import ack_statements


MAX_ATTEMPTS = 3
ALLOWED_OPERATIONS = frozenset({
    "SQL_BATCH", "CREATE_SCHEDULE", "AUTO_CREATE_SCHEDULE",
    "FIND_AVAILABLE_SLOTS", "POLL_REMINDERS", "ACK_REMINDER",
})
ERROR_CODES = frozenset({
    "INVALID_ARGUMENT", "TIME_CONFLICT", "POLICY_LIMIT", "NO_AVAILABLE_SLOT",
    "NOT_FOUND", "PERMISSION_DENIED", "SQL_NOT_ALLOWED", "IDEMPOTENCY_CONFLICT",
    "INTERNAL_ERROR",
})
# 这些错误可以通过 Agent 调整时间或 SQL/参数后再提交；鉴权、协议和内部
# 故障不能由 Agent 修正，因此不会触发 Agent 重试。
RETRYABLE_ERROR_CODES = frozenset({"TIME_CONFLICT", "NO_AVAILABLE_SLOT"})
HTTP_STATUS_BY_CODE = {
    "INVALID_ARGUMENT": 400,
    "SQL_NOT_ALLOWED": 400,
    "TIME_CONFLICT": 409,
    "NO_AVAILABLE_SLOT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "POLICY_LIMIT": 422,
    "NOT_FOUND": 404,
    "PERMISSION_DENIED": 403,
    "INTERNAL_ERROR": 500,
}
ALLOWED_TABLES = {
    "todos": {
        "id", "title", "priority", "deadline", "estimate_min", "scheduled",
        "done", "source", "raw_input", "timezone", "request_id", "auto_scheduled",
        "created_at", "updated_at",
    },
    "scheduled_tasks": {
        "id", "todo_id", "start_at", "end_at", "timezone", "schedule_source",
        "reminder_sent", "reminder_at", "reminder_status", "reminder_idempotency_key",
        "reminder_attempt_count", "reminder_last_attempt_at", "reminder_error",
        "done", "status", "created_at",
    },
    "calendar_events": {
        "id", "type_id", "title", "event_date", "start_time", "end_time", "note",
    },
    "sent_reminders": {"id", "scheduled_task_id", "sent_at", "idempotency_key"},
}

_CACHE_LIMIT = 512
_cache = OrderedDict()
_lock = RLock()
audit_log = logging.getLogger("audit")


def audit_event(event, *, request_id=None, operation=None, attempt=None,
                code=None, phase=None):
    """写入不含 SQL、参数或用户原文的安全审计事件。"""
    fields = {
        "event": event, "request_id": request_id, "operation": operation,
        "attempt": attempt, "code": code, "phase": phase,
    }
    rendered = " ".join(f"{key}={value!s}" for key, value in fields.items()
                        if value is not None)
    audit_log.warning(rendered)


class ExecutorError(ValueError):
    def __init__(self, code, message, *, retryable=None, http_status=None):
        if code not in ERROR_CODES:
            code = "INTERNAL_ERROR"
        if retryable is None:
            retryable = code in RETRYABLE_ERROR_CODES
        if http_status is None:
            http_status = HTTP_STATUS_BY_CODE[code]
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


def _error_response(request_id, attempt, error):
    return {
        "request_id": request_id,
        "success": False,
        "attempt": attempt,
        "retryable": error.retryable,
        "error": {"code": error.code, "message": error.message},
    }


def make_error_response(request_id, attempt, code, message):
    """构造统一错误协议，供后端业务模块复用。"""
    return _error_response(request_id, attempt, ExecutorError(code, message))


def http_status_for(response):
    """从错误响应映射稳定 HTTP 状态，不把内部状态字段放进 JSON。"""
    if response.get("success"):
        return 200
    return HTTP_STATUS_BY_CODE.get(response.get("error", {}).get("code"), 500)


def _success_response(request_id, attempt, results, *, idempotent=False, schedule=None):
    response = {
        "request_id": request_id,
        "success": True,
        "attempt": attempt,
        "transaction": "COMMITTED",
        "results": results,
    }
    if idempotent:
        response["idempotent_replay"] = True
    if schedule is not None:
        response["schedule"] = schedule
    return response


def _scan_unquoted(sql, predicate):
    quote = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote:
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            elif char == "\\" and quote in ("'", '"'):
                i += 2
                continue
        elif char in ("'", '"', "`"):
            quote = char
        elif predicate(sql, i):
            return True
        i += 1
    return False


def _placeholder_count(sql):
    count = 0
    quote = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote:
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            elif char == "\\" and quote in ("'", '"'):
                i += 2
                continue
        elif char in ("'", '"', "`"):
            quote = char
        elif char == "?":
            count += 1
        elif char == "%" and i + 1 < len(sql) and sql[i + 1] == "s":
            count += 1
            i += 1
        i += 1
    return count


def _to_parse_sql(sql):
    # sqlglot treats MySQL's %s binding marker as modulo syntax. Replace only
    # markers outside quoted strings; the original SQL is still sent to PyMySQL.
    out = []
    quote = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote:
            out.append(char)
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
            elif char == "\\" and quote in ("'", '"') and i + 1 < len(sql):
                out.append(sql[i + 1])
                i += 1
        elif char in ("'", '"', "`"):
            quote = char
            out.append(char)
        elif char == "%" and i + 1 < len(sql) and sql[i + 1] == "s":
            out.append("?")
            i += 1
        else:
            out.append(char)
        i += 1
    return "".join(out)


def _validate_statement(statement):
    if not isinstance(statement, dict):
        raise ExecutorError("INVALID_ARGUMENT", "每条 statement 必须是对象")
    sql = statement.get("sql")
    params = statement.get("params", [])
    if not isinstance(sql, str) or not sql.strip():
        raise ExecutorError("INVALID_ARGUMENT", "statement.sql 必须是非空字符串")
    if not isinstance(params, list):
        raise ExecutorError("INVALID_ARGUMENT", "statement.params 必须是数组")
    if _scan_unquoted(sql, lambda value, i: value.startswith("--", i)
                      or value.startswith("/*", i)
                      or value.startswith("#", i)):
        raise ExecutorError("SQL_NOT_ALLOWED", "SQL 不允许包含注释")
    if _scan_unquoted(sql, lambda value, i: value[i] == ";"):
        raise ExecutorError("SQL_NOT_ALLOWED", "SQL 不允许多语句或分号")
    if _placeholder_count(sql) != len(params):
        raise ExecutorError("INVALID_ARGUMENT", "SQL 占位符数量必须与参数数组一致")
    if re.search(r"\b(?:CALL|EXEC|EXECUTE|INTO\s+OUTFILE|LOAD\s+DATA)\b", sql, re.I):
        raise ExecutorError("SQL_NOT_ALLOWED", "SQL 操作不在允许范围内")

    try:
        tree = sqlglot.parse_one(_to_parse_sql(sql), read="mysql")
    except Exception as exc:
        raise ExecutorError("SQL_NOT_ALLOWED", "SQL 无法通过安全解析") from exc
    if not isinstance(tree, (exp.Select, exp.Insert, exp.Update)):
        raise ExecutorError("SQL_NOT_ALLOWED", "只允许 SELECT、INSERT、UPDATE")

    tables = {}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name not in ALLOWED_TABLES or table.db or table.catalog:
            raise ExecutorError("SQL_NOT_ALLOWED", "访问了未授权的表")
        tables[table.alias_or_name.lower()] = name
    if not tables:
        raise ExecutorError("SQL_NOT_ALLOWED", "SQL 必须访问白名单表")

    for column in tree.find_all(exp.Column):
        table_name = column.table.lower() if column.table else None
        resolved = tables.get(table_name, table_name) if table_name else None
        if resolved and resolved not in ALLOWED_TABLES:
            raise ExecutorError("SQL_NOT_ALLOWED", "字段引用了未授权的表")
        candidates = [ALLOWED_TABLES[t] for t in tables.values()]
        if not any(column.name.lower() in allowed for allowed in candidates):
            raise ExecutorError("SQL_NOT_ALLOWED", "访问了未授权的字段")
        if resolved and column.name.lower() not in ALLOWED_TABLES[resolved]:
            raise ExecutorError("SQL_NOT_ALLOWED", "访问了未授权的字段")

    for node in tree.walk():
        if (isinstance(node, exp.Func) and not isinstance(node, exp.Connector)) or \
                isinstance(node, (exp.Subquery, exp.Union, exp.Command)):
            raise ExecutorError("SQL_NOT_ALLOWED", "不允许函数、子查询或组合查询")

    if isinstance(tree, exp.Insert):
        target = tree.this
        target_name = target.this.name.lower() if isinstance(target, exp.Schema) else ""
        for column in target.expressions if isinstance(target, exp.Schema) else ():
            if column.name.lower() not in ALLOWED_TABLES.get(target_name, set()):
                raise ExecutorError("SQL_NOT_ALLOWED", "INSERT 包含未授权字段")
    elif isinstance(tree, exp.Update):
        target_name = tree.this.name.lower()
        for column in tree.find_all(exp.Column):
            if column.name.lower() not in ALLOWED_TABLES.get(target_name, set()):
                raise ExecutorError("SQL_NOT_ALLOWED", "UPDATE 包含未授权字段")

    return sql, params


def _validate_request(payload):
    if not isinstance(payload, dict):
        raise ExecutorError("INVALID_ARGUMENT", "请求体必须是 JSON 对象")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 64:
        raise ExecutorError("INVALID_ARGUMENT", "request_id 必须是 1 到 64 个字符")
    attempt = payload.get("attempt", 1)
    max_attempts = payload.get("max_attempts", MAX_ATTEMPTS)
    if not isinstance(attempt, int) or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ExecutorError("INVALID_ARGUMENT", "attempt 必须在 1 到 3 之间")
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ExecutorError("INVALID_ARGUMENT", "max_attempts 必须在 1 到 3 之间")
    if attempt > max_attempts:
        raise ExecutorError("INVALID_ARGUMENT", "attempt 不能大于 max_attempts")
    operation = payload.get("operation", "SQL_BATCH")
    if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
        raise ExecutorError("INVALID_ARGUMENT", "operation 必须是非空字符串")
    if operation not in ALLOWED_OPERATIONS:
        raise ExecutorError("SQL_NOT_ALLOWED", "operation 不在允许范围内")
    statements = payload.get("statements")
    if not isinstance(statements, list) or not statements:
        raise ExecutorError("INVALID_ARGUMENT", "statements 必须是非空数组")
    validated = [_validate_statement(statement) for statement in statements]
    if operation in {"SQL_BATCH", "POLL_REMINDERS"}:
        # 通用批次和提醒轮询都不得借用合法字段直接写入业务表；写操作
        # 必须走 CREATE/ACK 专用模板校验。
        for sql, _ in validated:
            try:
                tree = sqlglot.parse_one(_to_parse_sql(sql), read="mysql")
            except Exception as exc:
                raise ExecutorError("SQL_NOT_ALLOWED", "SQL 无法通过安全解析") from exc
            if not isinstance(tree, exp.Select):
                raise ExecutorError("SQL_NOT_ALLOWED", f"{operation} 只允许 SELECT")
    if operation == "ACK_REMINDER":
        _validate_ack_request(payload, validated)
    return request_id, attempt, operation, validated


def _validate_ack_request(payload, statements):
    task_id = payload.get("scheduled_task_id")
    key = payload.get("idempotency_key")
    status = payload.get("status")
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
        raise ExecutorError("INVALID_ARGUMENT", "scheduled_task_id 必须是正整数")
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise ExecutorError("INVALID_ARGUMENT", "idempotency_key 必须是 1 到 128 个字符")
    if status not in {"SENT", "FAILED"}:
        raise ExecutorError("INVALID_ARGUMENT", "status 必须是 SENT 或 FAILED")
    if status == "SENT" and len(statements) != 2:
        raise ExecutorError("INVALID_ARGUMENT", "SENT 确认必须原子更新并写入成功记录")
    if status == "FAILED" and len(statements) != 1:
        raise ExecutorError("INVALID_ARGUMENT", "FAILED 确认只能更新排期状态")
    update_params = statements[0][1]
    if task_id not in update_params or key not in update_params:
        raise ExecutorError("IDEMPOTENCY_CONFLICT", "确认 SQL 的排期 ID 或幂等键不一致")
    if status == "SENT" and len(statements) == 2:
        insert_params = statements[1][1]
        if task_id not in insert_params or key not in insert_params:
            raise ExecutorError("IDEMPOTENCY_CONFLICT", "成功记录的排期 ID 或幂等键不一致")
    if len(update_params) != 7:
        raise ExecutorError("SQL_NOT_ALLOWED", "提醒确认必须使用受限更新模板")
    stamp = payload.get("ack_at", update_params[4])
    _parse_utc_datetime(stamp, "ack_at")
    error = payload.get("error", update_params[5])
    if error is not None and (not isinstance(error, str) or len(error) > 1000):
        raise ExecutorError("INVALID_ARGUMENT", "error 必须是至多 1000 个字符的字符串")
    if status == "SENT" and error is not None:
        raise ExecutorError("INVALID_ARGUMENT", "成功确认不能包含失败原因")
    expected = ack_statements(task_id, key, status, stamp, error)
    for (sql, params), template in zip(statements, expected):
        if (re.sub(r"\s+", "", sql).lower() != re.sub(r"\s+", "", template["sql"]).lower()
                or list(params) != template["params"]):
            raise ExecutorError("SQL_NOT_ALLOWED", "提醒确认 SQL 或绑定参数与发送结果不一致")


def _insert_bindings(sql, params):
    """返回 INSERT 的目标表、字段到绑定值的映射及值参数下标。"""
    tree = sqlglot.parse_one(_to_parse_sql(sql), read="mysql")
    if not isinstance(tree, exp.Insert) or not isinstance(tree.this, exp.Schema):
        return None
    values = tree.expression
    if not isinstance(values, exp.Values) or len(values.expressions) != 1:
        return None
    row = values.expressions[0].expressions
    columns = [item.name.lower() for item in tree.this.expressions]
    if len(columns) != len(row):
        return None
    bindings = {}
    param_index = 0
    for column, value in zip(columns, row):
        if not isinstance(value, exp.Placeholder):
            return None
        bindings[column] = params[param_index]
        param_index += 1
    return tree.this.this.name.lower(), bindings


def _parse_utc_datetime(value, field):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExecutorError("INVALID_ARGUMENT", f"{field} 时间格式无效") from exc
    else:
        raise ExecutorError("INVALID_ARGUMENT", f"{field} 必须是时间值")
    if result.tzinfo:
        result = result.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return result


def _create_schedule_metadata(request_id, statements, *, auto_scheduled=False):
    inserts = []
    for index, (sql, params) in enumerate(statements):
        binding = _insert_bindings(sql, params)
        if binding:
            inserts.append((index, binding[0], binding[1]))
    todos = [item for item in inserts if item[1] == "todos"]
    schedules = [item for item in inserts if item[1] == "scheduled_tasks"]
    if len(statements) != 2 or len(todos) != 1 or len(schedules) != 1:
        raise ExecutorError("INVALID_ARGUMENT", "CREATE_SCHEDULE 必须包含各一条 todos 和 scheduled_tasks INSERT")
    todo_index, _, todo = todos[0]
    schedule_index, _, schedule = schedules[0]
    if todo_index >= schedule_index:
        raise ExecutorError("INVALID_ARGUMENT", "CREATE_SCHEDULE 必须先插入 todos 再插入 scheduled_tasks")
    title = todo.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        raise ExecutorError("INVALID_ARGUMENT", "日程标题必须是 1 到 500 个字符")
    if todo.get("request_id") != request_id:
        raise ExecutorError("INVALID_ARGUMENT", "todos.request_id 必须与请求 request_id 一致")
    if type(todo.get("auto_scheduled", 0)) is not int or todo.get("auto_scheduled", 0) != int(auto_scheduled):
        raise ExecutorError("INVALID_ARGUMENT", "auto_scheduled 与创建操作不一致")
    timezone = todo.get("timezone") or schedule.get("timezone") or "Asia/Shanghai"
    if any(value.get("timezone", timezone) != timezone for value in (todo, schedule)):
        raise ExecutorError("INVALID_ARGUMENT", "待办与排期的 timezone 必须一致")
    try:
        ZoneInfo(str(timezone))
    except Exception as exc:
        raise ExecutorError("INVALID_ARGUMENT", "timezone 必须是有效的 IANA 时区") from exc
    start_at = _parse_utc_datetime(schedule.get("start_at"), "start_at")
    end_at = _parse_utc_datetime(schedule.get("end_at"), "end_at")
    if end_at <= start_at:
        raise ExecutorError("INVALID_ARGUMENT", "end_at 必须晚于 start_at")
    estimate = todo.get("estimate_min")
    if estimate is not None and (type(estimate) is not int or estimate <= 0
                               or end_at - start_at != timedelta(minutes=estimate)):
        raise ExecutorError("INVALID_ARGUMENT", "estimate_min 必须是正整数且与时间段一致")
    priority = todo.get("priority", 2)
    if type(priority) is not int or priority not in (1, 2, 3):
        raise ExecutorError("INVALID_ARGUMENT", "priority 必须是 1、2 或 3")
    for values, required in (
        (todo, {"done": 0, "scheduled": 1}),
        (schedule, {"done": 0, "reminder_sent": 0, "status": "ACTIVE",
                    "reminder_status": "PENDING", "reminder_attempt_count": 0}),
    ):
        for field, expected in required.items():
            if field in values and (type(values[field]) is not type(expected) or values[field] != expected):
                raise ExecutorError("INVALID_ARGUMENT", f"新日程的 {field} 必须为 {expected}")
    reminder_at = schedule.get("reminder_at")
    if reminder_at is not None:
        reminder_at = _parse_utc_datetime(reminder_at, "reminder_at")
        if reminder_at > start_at:
            raise ExecutorError("INVALID_ARGUMENT", "reminder_at 不能晚于 start_at")
    source = schedule.get("schedule_source", "MANUAL")
    expected_source = "AUTO" if auto_scheduled else "MANUAL"
    if source != expected_source:
        raise ExecutorError("INVALID_ARGUMENT", f"创建的 schedule_source 必须为 {expected_source}")
    if "todo_id" not in schedule or "created_at" not in todo or "updated_at" not in todo:
        raise ExecutorError("INVALID_ARGUMENT", "CREATE_SCHEDULE 缺少必填持久化字段")
    deadline = _parse_deadline(todo.get("deadline"), str(timezone))
    if deadline and end_at > deadline:
        if auto_scheduled:
            raise ExecutorError("NO_AVAILABLE_SLOT", "截止时间前没有可用的完整时间段")
        raise ExecutorError("INVALID_ARGUMENT", "end_at 不能晚于 deadline")
    return {
        "todo_index": todo_index,
        "schedule_index": schedule_index,
        "schedule_param_index": next((i for i, key in enumerate(_insert_bindings(statements[schedule_index][0], statements[schedule_index][1])[1]) if key == "todo_id"), None),
        "start_at": start_at,
        "end_at": end_at,
        "timezone": str(timezone),
        "reminder_at": reminder_at,
        "auto_scheduled": auto_scheduled,
        "deadline": deadline,
    }


def _normalize_create_statements(statements, metadata):
    """校验和写入使用同一组 UTC 值，补齐新日程初始状态。"""
    normalized = []
    allowed = {
        "todos": {"title", "priority", "deadline", "estimate_min", "source", "raw_input",
                  "timezone", "request_id", "auto_scheduled", "created_at", "updated_at",
                  "scheduled", "done"},
        "scheduled_tasks": {"todo_id", "start_at", "end_at", "timezone", "schedule_source",
                            "reminder_at", "reminder_status", "created_at", "status", "done",
                            "reminder_sent", "reminder_idempotency_key", "reminder_attempt_count"},
    }
    for sql, params in statements:
        table, values = _insert_bindings(sql, params)
        if not set(values) <= allowed[table]:
            raise ExecutorError("INVALID_ARGUMENT", "创建日程包含不允许的初始字段")
        values["timezone"] = metadata["timezone"]
        values["done"] = 0
        if table == "todos":
            values["scheduled"] = 1
            values["auto_scheduled"] = int(metadata["auto_scheduled"])
            if "deadline" in values:
                values["deadline"] = metadata["deadline"]
        else:
            values.update(start_at=metadata["start_at"], end_at=metadata["end_at"],
                          reminder_at=metadata["reminder_at"], status="ACTIVE",
                          schedule_source="AUTO" if metadata["auto_scheduled"] else "MANUAL",
                          reminder_sent=0, reminder_status="PENDING", reminder_attempt_count=0)
        for field in ("created_at", "updated_at"):
            if field in values:
                values[field] = _parse_utc_datetime(values[field], field)
        columns = list(values)
        normalized.append((f"INSERT INTO {table} ({','.join(columns)}) "
                           f"VALUES ({','.join(['%s'] * len(columns))})", list(values.values())))
    return normalized


def _parse_local_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ExecutorError("INVALID_ARGUMENT", "date 必须是 YYYY-MM-DD") from exc
    raise ExecutorError("INVALID_ARGUMENT", "date 必须是 YYYY-MM-DD")


def _parse_deadline(value, timezone):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExecutorError("INVALID_ARGUMENT", "deadline 时间格式无效") from exc
    else:
        raise ExecutorError("INVALID_ARGUMENT", "deadline 时间格式无效")
    if parsed.tzinfo:
        return parsed.astimezone(ZoneInfo(timezone)).replace(tzinfo=None)
    return parsed


def _available_metadata(payload):
    try:
        return query_metadata(payload, datetime.now(ZoneInfo("UTC")))
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ExecutorError("INVALID_ARGUMENT", str(exc)) from exc


def _validate_available_statements(statements, metadata):
    expected = occupancy_statements(metadata)
    if len(statements) != len(expected):
        raise ExecutorError("SQL_NOT_ALLOWED", "必须同时查询两类占用")
    for (sql, params), template in zip(statements, expected):
        actual = sqlglot.parse_one(_to_parse_sql(sql), read="mysql")
        required = sqlglot.parse_one(_to_parse_sql(template["sql"]), read="mysql")
        if actual != required or list(params) != template["params"]:
            raise ExecutorError("SQL_NOT_ALLOWED", "占用查询必须使用受限范围和有效状态")


def _check_schedule_conflict(cursor, metadata):
    cursor.execute(
        "SELECT id FROM scheduled_tasks "
        "WHERE status='ACTIVE' AND start_at < %s AND end_at > %s FOR UPDATE",
        (metadata["end_at"], metadata["start_at"]),
    )
    if cursor.fetchone():
        raise ExecutorError("TIME_CONFLICT", "时间段与已有排期冲突")
    local_start = metadata["start_at"].replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(metadata["timezone"]))
    local_end = metadata["end_at"].replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(metadata["timezone"]))
    cursor.execute(
        "SELECT event_date,start_time,end_time FROM calendar_events "
        "WHERE event_date BETWEEN %s AND %s",
        (local_start.date(), local_end.date()),
    )
    for row in cursor.fetchall():
        event_start_time = row["start_time"]
        event_end_time = row["end_time"]
        # PyMySQL maps MySQL TIME values to timedelta when the value is not
        # representable as a Python time; normalize both forms.
        if isinstance(event_start_time, timedelta):
            event_start_time = (datetime.min + event_start_time).time()
        if isinstance(event_end_time, timedelta):
            event_end_time = (datetime.min + event_end_time).time()
        if not isinstance(event_start_time, time) or not isinstance(event_end_time, time):
            raise ExecutorError("INTERNAL_ERROR", "日历事件时间数据无效")
        event_start = datetime.combine(row["event_date"], event_start_time)
        event_end = datetime.combine(row["event_date"], event_end_time)
        if event_start < local_end.replace(tzinfo=None) and event_end > local_start.replace(tzinfo=None):
            raise ExecutorError("TIME_CONFLICT", "时间段与手动日历事件冲突")


def _replay_created_schedule(cursor, request_id, attempt):
    """从既有唯一请求键恢复已提交结果，不依赖进程缓存或当前候选时间。"""
    cursor.execute(
        "SELECT t.id AS todo_id,t.auto_scheduled,s.id AS scheduled_task_id,"
        "s.start_at,s.end_at,s.timezone,s.reminder_at FROM todos t "
        "JOIN scheduled_tasks s ON s.todo_id=t.id WHERE t.request_id=%s",
        (request_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise ExecutorError("IDEMPOTENCY_CONFLICT", "请求关联的排期记录不唯一")
    row = rows[0]
    schedule = {key: row[key] for key in ("todo_id", "scheduled_task_id", "timezone")}
    for key in ("start_at", "end_at", "reminder_at"):
        schedule[key] = row[key].isoformat(sep=" ") if row[key] is not None else None
    for key in ("start_at", "end_at", "reminder_at"):
        value = row[key]
        schedule[key + "_local"] = (
            value.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(str(row["timezone"]))).isoformat(sep=" ")
            if value is not None else None
        )
    schedule["auto_scheduled"] = bool(row["auto_scheduled"])
    results = [{"statement_index": index, "row_count": 1, "last_insert_id": row[key]}
               for index, key in enumerate(("todo_id", "scheduled_task_id"))]
    return _success_response(request_id, attempt, results, idempotent=True, schedule=schedule)


def _json_value(value):
    """Serialize database temporal values explicitly as ISO UTC values."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return (datetime.min + value).time().isoformat()
    return value


def _recover_created_schedule(request_id, attempt):
    # 唯一键竞争失败的事务已经回滚；新连接可见另一进程刚提交的结果。
    with db.get_conn() as conn, conn.cursor() as cursor:
        return _replay_created_schedule(cursor, request_id, attempt)


def execute(payload):
    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    attempt = payload.get("attempt", 1) if isinstance(payload, dict) else 1
    try:
        request_id, attempt, operation, statements = _validate_request(payload)
        schedule_metadata = None
        if operation in {"CREATE_SCHEDULE", "AUTO_CREATE_SCHEDULE"}:
            schedule_metadata = _create_schedule_metadata(
                request_id, statements, auto_scheduled=operation == "AUTO_CREATE_SCHEDULE"
            )
            statements = _normalize_create_statements(statements, schedule_metadata)
        available_metadata = _available_metadata(payload) if operation == "FIND_AVAILABLE_SLOTS" else None
        if available_metadata:
            _validate_available_statements(statements, available_metadata)
    except ExecutorError as error:
        audit_event("request_rejected", request_id=request_id,
                    operation=(payload.get("operation") if isinstance(payload, dict) else None),
                    attempt=attempt, code=error.code, phase="validation")
        return _error_response(request_id, attempt, error)

    with _lock:
        # 提醒轮询必须读取最新状态，不能重放确认发送之前的查询结果。
        cached = _cache.get(request_id) if operation not in {"POLL_REMINDERS", "FIND_AVAILABLE_SLOTS"} else None
        if cached is not None:
            return dict(cached, idempotent_replay=True)
        try:
            with db.get_conn() as conn:
                results = []
                generated_todo_id = None
                with conn.cursor() as cursor:
                    if schedule_metadata:
                        replay = _replay_created_schedule(cursor, request_id, attempt)
                        if replay is not None:
                            return replay
                    if operation == "ACK_REMINDER":
                        task_id = payload["scheduled_task_id"]
                        key = payload["idempotency_key"]
                        cursor.execute(
                            "SELECT reminder_status,reminder_idempotency_key FROM scheduled_tasks WHERE id=%s FOR UPDATE",
                            (task_id,),
                        )
                        existing = cursor.fetchone()
                        if not existing:
                            raise ExecutorError("NOT_FOUND", "提醒排期不存在")
                        existing_key = existing.get("reminder_idempotency_key")
                        if existing_key and existing_key != key:
                            raise ExecutorError("IDEMPOTENCY_CONFLICT", "提醒幂等键与原记录不一致")
                        # 成功发送是终态；迟到的失败确认也不能撤销成功记录。
                        if existing.get("reminder_status") == "SENT":
                            response = _success_response(request_id, attempt, [], idempotent=True)
                            return response
                    if schedule_metadata:
                        _check_schedule_conflict(cursor, schedule_metadata)
                    for index, (sql, params) in enumerate(statements):
                        params = list(params)
                        if schedule_metadata and index == schedule_metadata["schedule_index"] and generated_todo_id:
                            binding = _insert_bindings(sql, params)
                            if binding:
                                columns = list(binding[1])
                                todo_id_pos = columns.index("todo_id")
                                params[todo_id_pos] = generated_todo_id
                        cursor.execute(sql, tuple(params))
                        rows = cursor.fetchall() if cursor.description else []
                        result = {
                            "statement_index": index,
                            "row_count": len(rows) if cursor.description else cursor.rowcount,
                            "last_insert_id": cursor.lastrowid or None,
                        }
                        if cursor.description:
                            if available_metadata:
                                result["rows"] = [
                                    {key: _json_value(value)
                                     for key, value in row.items()} for row in rows
                                ]
                            else:
                                result["rows"] = [
                                    {key: _json_value(value) for key, value in row.items()}
                                    for row in rows
                                ]
                        results.append(result)
                        if schedule_metadata and index == schedule_metadata["todo_index"]:
                            generated_todo_id = cursor.lastrowid
            schedule = None
            if schedule_metadata:
                todo_result = results[schedule_metadata["todo_index"]]
                task_result = results[schedule_metadata["schedule_index"]]
                schedule = {
                    "todo_id": todo_result["last_insert_id"],
                    "scheduled_task_id": task_result["last_insert_id"],
                    "start_at": schedule_metadata["start_at"].isoformat(sep=" "),
                    "end_at": schedule_metadata["end_at"].isoformat(sep=" "),
                    "timezone": schedule_metadata["timezone"],
                    "reminder_at": (
                        schedule_metadata["reminder_at"].isoformat(sep=" ")
                        if schedule_metadata["reminder_at"] else None
                    ),
                    "auto_scheduled": schedule_metadata["auto_scheduled"],
                }
                for key in ("start_at", "end_at", "reminder_at"):
                    value = schedule_metadata[key]
                    schedule[key + "_local"] = (
                        value.replace(tzinfo=ZoneInfo("UTC")).astimezone(
                            ZoneInfo(str(schedule_metadata["timezone"]))
                        ).isoformat(sep=" ") if value is not None else None
                    )
            response = _success_response(request_id, attempt, results, schedule=schedule)
            if operation not in {"POLL_REMINDERS", "FIND_AVAILABLE_SLOTS"}:
                _cache[request_id] = response
                _cache.move_to_end(request_id)
            while len(_cache) > _CACHE_LIMIT:
                _cache.popitem(last=False)
            return response
        except ExecutorError as error:
            audit_event("request_rejected", request_id=request_id,
                        operation=operation, attempt=attempt,
                        code=error.code, phase="execution")
            if schedule_metadata and error.code == "TIME_CONFLICT":
                try:
                    replay = _recover_created_schedule(request_id, attempt)
                    if replay is not None:
                        return replay
                except Exception:
                    return make_error_response(request_id, attempt, "INTERNAL_ERROR", "数据库执行失败")
            return _error_response(request_id, attempt, error)
        except Exception as exc:
            # MySQL 1062：可能是并发的同请求创建，也可能是其他唯一键冲突。
            # 只有已提交且同 request_id 的日程才可作为成功重放。
            if schedule_metadata and getattr(exc, "args", ()) and exc.args[0] == 1062:
                try:
                    replay = _recover_created_schedule(request_id, attempt)
                    if replay is not None:
                        return replay
                except Exception:
                    pass
            error = ExecutorError("INTERNAL_ERROR", "数据库执行失败")
            audit_event("request_failed", request_id=request_id,
                        operation=operation, attempt=attempt,
                        code=error.code, phase="database")
            return _error_response(request_id, attempt, error)
