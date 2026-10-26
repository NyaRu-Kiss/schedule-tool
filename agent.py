"""WorkBuddy 日程 Agent。

Agent 只负责自然语言解析、受限 SQL 生成、自动排期选择和有限重试。
``backend_call`` 由 MCP/HTTP 适配层注入，Agent 不连接数据库。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reminder_sql import ack_statements
from availability import query_metadata, occupancy_statements, compute_slots
from llm import IntentParseError, intent_parser_from_env


MAX_ATTEMPTS = 3
DEFAULT_DURATION_MIN = 30


def error_response(code: str, message: str, *, retryable=False) -> dict:
    """统一业务错误格式；内部故障和参数错误不可由 Agent 修正。"""
    return {"success": False, "retryable": retryable,
            "error": {"code": code, "message": message}}


def _cn_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if value.startswith("十"):
        return 10 + (digits.get(value[1:], 0) if len(value) > 1 else 0)
    if "十" in value:
        left, right = value.split("十", 1)
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    raise ValueError(value)


def _extract_duration(text: str) -> int:
    match = re.search(r"(?:安排|用|时长|持续)?\s*(\d+|[一二两三四五六七八九十]+)\s*个?小时", text)
    if match:
        return _cn_number(match.group(1)) * 60
    match = re.search(r"(?:安排|用|时长|持续)?\s*(\d+|[一二两三四五六七八九十]+)\s*分钟", text)
    if match:
        return _cn_number(match.group(1))
    return DEFAULT_DURATION_MIN


def _extract_reminder(text: str, start: datetime | None) -> datetime | None:
    if not start or not re.search(r"提醒|通知", text):
        return None
    match = re.search(r"提前\s*(\d+|[一二两三四五六七八九十]+)\s*分钟", text)
    minutes = _cn_number(match.group(1)) if match else 5
    return start - timedelta(minutes=minutes)


def _extract_datetime(text: str, now: datetime) -> tuple[datetime | None, str]:
    target_date = now.date()
    if "后天" in text:
        target_date += timedelta(days=2)
    elif "明天" in text:
        target_date += timedelta(days=1)
    elif "今天" in text:
        target_date = now.date()
    date_match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?", text)
    if date_match:
        target_date = target_date.replace(year=int(date_match.group(1)), month=int(date_match.group(2)), day=int(date_match.group(3)))

    match = re.search(r"(上午|下午|晚上|早上)?\s*(\d{1,2}|[一二两三四五六七八九十]+)(?:点|时)(?:(\d{1,2})分?)?", text)
    if not match:
        match = re.search(r"(上午|下午|晚上|早上)?\s*(\d{1,2}):(\d{2})", text)
        if not match:
            return None, target_date.isoformat()
        period, hour_text, minute_text = match.groups()
    else:
        period, hour_text, minute_text = match.groups()
    hour = _cn_number(hour_text)
    minute = int(minute_text or 0)
    if period in ("下午", "晚上") and hour < 12:
        hour += 12
    if period in ("上午", "早上") and hour == 12:
        hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("时间超出范围")
    return datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute), target_date.isoformat()


def _extract_title(text: str) -> str:
    title = re.sub(r"(?:今天|明天|后天|提前\s*\S+?分钟|上午|下午|晚上|早上)", "", text)
    title = re.sub(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?", "", title)
    title = re.sub(r"(?:\d{1,2}|[一二两三四五六七八九十]+)(?::\d{2}|点(?:\d{1,2}分?)?)", "", title)
    title = re.sub(r"(?:安排|帮我|提醒我|通知我|要|需要|准备|在|于|做|用)?\s*(?:\d+|[一二两三四五六七八九十]+)\s*个?小时", "", title)
    title = re.sub(r"(?:安排|帮我|提醒我|通知我|日程|日子)", "", title)
    title = re.sub(r"[，。,.、；;]", " ", title)
    return re.sub(r"\s+", " ", title).strip() or "未命名日程"


class AgendaAgent:
    def __init__(self, backend_call: Callable[[dict], dict], *, timezone="Asia/Shanghai", clock=None,
                 intent_parser=None):
        self.backend_call = backend_call
        self.timezone = timezone
        self.clock = clock or (lambda: datetime.now(ZoneInfo(timezone)))
        self.intent_parser = intent_parser

    def _request(self, payload, *, attempts, attempt_start=1):
        last = None
        for attempt in range(attempt_start, min(MAX_ATTEMPTS, attempt_start + attempts - 1) + 1):
            request = dict(payload, attempt=attempt, max_attempts=MAX_ATTEMPTS)
            last = self.backend_call(request)
            if last.get("success") or not last.get("retryable") or attempt == MAX_ATTEMPTS:
                return last
        return last

    def create_schedule(self, text: str, request_id: str, *, timezone=None):
        if not isinstance(text, str) or not text.strip():
            return error_response("INVALID_ARGUMENT", "用户文本不能为空", retryable=False)
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 64:
            return error_response("INVALID_ARGUMENT", "request_id 必须是 1 到 64 个字符")
        requested_timezone = timezone
        timezone = timezone or self.timezone
        try:
            zone = ZoneInfo(timezone)
            now = self.clock().astimezone(zone)
            parser = self.intent_parser if self.intent_parser is not None else intent_parser_from_env()
            if parser is None:
                start, target_date = _extract_datetime(text, now)
                duration = _extract_duration(text)
                title = _extract_title(text)
                reminder_requested = bool(re.search(r"提醒|通知", text))
                reminder_minutes = None
            else:
                try:
                    intent = parser.parse(text, timezone=timezone, today=now.date())
                except Exception as exc:
                    raise IntentParseError("无法解析日程意图") from exc
                if intent["needs_clarification"]:
                    return {"success": False, "retryable": False,
                            "error": {"code": "NEEDS_CLARIFICATION",
                                      "message": intent["clarification_question"]},
                            "needs_clarification": True,
                            "clarification_question": intent["clarification_question"]}
                if intent["timezone"] and requested_timezone is None:
                    timezone = intent["timezone"]
                    zone = ZoneInfo(timezone)
                title = intent["title"].strip()
                if not title:
                    raise ValueError("标题不能为空")
                target_date = date.fromisoformat(intent["date"]).isoformat()
                start = (datetime.combine(date.fromisoformat(target_date), datetime.strptime(
                    intent["start_time"], "%H:%M").time()) if intent["start_time"] else None)
                duration = intent["duration_min"] or DEFAULT_DURATION_MIN
                reminder_requested = intent["reminder_requested"]
                reminder_minutes = intent["reminder_minutes"]
                if (intent["timezone"] and requested_timezone is not None
                        and ZoneInfo(intent["timezone"]) != zone):
                    raise ValueError("识别到的时区与请求时区不一致")
                if reminder_minutes is not None and not reminder_requested:
                    raise ValueError("未请求提醒却返回了提醒时间")
        except IntentParseError:
            return error_response("INTENT_PARSE_FAILED", "无法可靠解析日程，请调整描述后重试")
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return error_response("INVALID_ARGUMENT", "时间或时区无效")
        stamp = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None).replace(microsecond=0).isoformat(sep=" ")
        def create_payload(start, end, *, auto_scheduled):
            start_utc = start.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            end_utc = end.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            reminder = ((start - timedelta(minutes=reminder_minutes if reminder_minutes is not None else 5))
                        if start and reminder_requested else None)
            reminder_utc = (reminder.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                            if reminder else None)
            return {
                "request_id": request_id,
                "operation": "AUTO_CREATE_SCHEDULE" if auto_scheduled else "CREATE_SCHEDULE",
                "statements": [
                    {"sql": "INSERT INTO todos (title,priority,estimate_min,source,raw_input,timezone,request_id,auto_scheduled,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", "params": [title, 2, duration, "workbuddy", text, timezone, request_id, int(auto_scheduled), stamp, stamp]},
                    {"sql": "INSERT INTO scheduled_tasks (todo_id,start_at,end_at,timezone,schedule_source,reminder_at,reminder_status,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", "params": [0, start_utc.isoformat(sep=" "), end_utc.isoformat(sep=" "), timezone, "AUTO" if auto_scheduled else "MANUAL", reminder_utc.isoformat(sep=" ") if reminder_utc else None, "PENDING", stamp]},
                ],
            }

        if start is not None:
            return self._request(create_payload(start, start + timedelta(minutes=duration), auto_scheduled=False),
                                 attempts=MAX_ATTEMPTS)

        # Automatic scheduling is a complete logical round: query, choose, create.
        # A conflict invalidates the chosen slot, so the next round must query again.
        last = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            available = self.find_available_slots(request_id, date=target_date,
                                                   duration_min=duration, timezone=timezone,
                                                   attempt=attempt)
            if not available.get("success"):
                # A retryable backend query failure consumes this round. No
                # slots means a completed query found nothing to create.
                if (available.get("retryable") and attempt < MAX_ATTEMPTS
                        and available.get("error", {}).get("code") != "NO_AVAILABLE_SLOT"):
                    continue
                return available
            slots = available.get("slots") or []
            if not slots:
                return error_response("NO_AVAILABLE_SLOT", "没有可用时间段", retryable=True)
            selected = slots[0]
            selected_start = datetime.fromisoformat(selected["start_at"])
            selected_end = datetime.fromisoformat(selected["end_at"])
            payload = create_payload(selected_start, selected_end, auto_scheduled=True)
            last = self.backend_call(dict(payload, attempt=attempt, max_attempts=MAX_ATTEMPTS))
            if last.get("success") or not last.get("retryable") or attempt == MAX_ATTEMPTS:
                return last
        return last

    def find_available_slots(self, request_id, *, date, end_date=None,
                             duration_min=30, timezone=None, deadline=None, attempt=None):
        """只查询占用并在 Agent 计算候选；不写入日程。"""
        payload = dict(request_id=request_id, operation="FIND_AVAILABLE_SLOTS",
                       date=date, end_date=end_date or date, duration_min=duration_min,
                       timezone=timezone or self.timezone, deadline=deadline)
        try:
            if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 64:
                raise ValueError("request_id 必须是 1 到 64 个字符")
            now = self.clock()
            metadata = query_metadata(payload, now)
            payload["statements"] = occupancy_statements(metadata)
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            return error_response("INVALID_ARGUMENT", str(exc))
        response = self._request(payload, attempts=1 if attempt else MAX_ATTEMPTS,
                                 attempt_start=attempt or 1)
        if not response.get("success"):
            return response
        slots = compute_slots(metadata, response.get("results", []), now)
        if not slots:
            return error_response("NO_AVAILABLE_SLOT", "指定范围内没有可用时间段", retryable=True)
        return dict(response, slots=slots)

    def poll_reminders(self, request_id: str, *, now=None, limit=100):
        """查询已经到期、仍有效且尚未发送的提醒。

        ``now`` 在接口边界可以是带时区的 ISO 时间；Agent 统一转换为 UTC
        传给后端。查询结果由后端返回，Agent 只负责透传并提取提醒列表，
        不在本地修改提醒状态。
        """
        if not isinstance(request_id, str) or not request_id.strip():
            return error_response("INVALID_ARGUMENT", "request_id 不能为空", retryable=False)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            return error_response("INVALID_ARGUMENT", "limit 必须是 1 到 100 的整数", retryable=False)
        try:
            current = now or self.clock()
            if isinstance(current, str):
                current = datetime.fromisoformat(current.replace("Z", "+00:00"))
            if not isinstance(current, datetime):
                raise ValueError("now must be datetime or ISO string")
            if current.tzinfo is None:
                current = current.replace(tzinfo=ZoneInfo(self.timezone))
            current_utc = current.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return error_response("INVALID_ARGUMENT", "now 必须是有效的时间值", retryable=False)

        payload = {
            "request_id": request_id,
            "operation": "POLL_REMINDERS",
            "statements": [
                {
                    "sql": (
                        "SELECT s.id AS scheduled_task_id, t.title, "
                        "s.start_at, s.end_at, s.reminder_at, s.timezone, "
                        "s.reminder_idempotency_key "
                        "FROM scheduled_tasks s JOIN todos t ON t.id=s.todo_id "
                        "WHERE s.reminder_status IN (%s,%s) AND s.reminder_at IS NOT NULL "
                        "AND s.reminder_at <= %s AND s.reminder_sent=%s "
                        "AND s.done=%s AND s.status=%s AND t.done=%s "
                        "ORDER BY s.reminder_at ASC, s.id ASC LIMIT %s"
                    ),
                    "params": ["PENDING", "FAILED", current_utc.isoformat(sep=" "), 0, 0, "ACTIVE", 0, limit],
                }
            ],
        }
        response = self._request(payload, attempts=MAX_ATTEMPTS)
        if response.get("success"):
            rows = []
            for result in response.get("results", []):
                if isinstance(result, dict) and isinstance(result.get("rows"), list):
                    rows.extend(result["rows"])
            response = dict(response)
            # 历史记录和当前创建流程允许该列为空。以排期 ID 生成稳定键，
            # 同一提醒在不同轮询及失败重试时使用相同的键。
            rows = [dict(row, reminder_idempotency_key=(
                row.get("reminder_idempotency_key") or f"reminder:{row['scheduled_task_id']}"
            )) for row in rows]
            for row in rows:
                zone = ZoneInfo(str(row.get("timezone") or self.timezone))
                for field in ("start_at", "end_at", "reminder_at"):
                    if row.get(field):
                        value = datetime.fromisoformat(str(row[field])).replace(tzinfo=ZoneInfo("UTC"))
                        row[field + "_local"] = value.astimezone(zone).isoformat(sep=" ")
            response["reminders"] = rows
        return response

    def ack_reminder(self, request_id, scheduled_task_id, idempotency_key, *,
                     status="SENT", error=None, now=None):
        """通过后端事务确认发送结果；失败提醒保留供下一轮轮询。"""
        try:
            if (not isinstance(request_id, str) or not request_id.strip()
                    or len(request_id) > 64):
                raise ValueError("request_id 必须是 1 到 64 个字符")
            if (isinstance(scheduled_task_id, bool) or not isinstance(scheduled_task_id, int)
                    or scheduled_task_id <= 0):
                raise ValueError("scheduled_task_id 必须是正整数")
            if (not isinstance(idempotency_key, str) or not idempotency_key.strip()
                    or len(idempotency_key) > 128):
                raise ValueError("idempotency_key 必须是 1 到 128 个字符")
            if status not in ("SENT", "FAILED"):
                raise ValueError("status 必须是 SENT 或 FAILED")
            if error is not None and (not isinstance(error, str) or len(error) > 1000):
                raise ValueError("error 必须是至多 1000 个字符的字符串")
            current = self.clock() if now is None else now
            if isinstance(current, str):
                current = datetime.fromisoformat(current.replace("Z", "+00:00"))
            if not isinstance(current, datetime):
                raise ValueError("now 必须是有效的时间值")
            if current.tzinfo is None:
                current = current.replace(tzinfo=ZoneInfo(self.timezone))
            stamp = current.astimezone(ZoneInfo("UTC")).replace(tzinfo=None).isoformat(sep=" ")
        except (TypeError, ValueError) as exc:
            return error_response("INVALID_ARGUMENT", str(exc), retryable=False)
        return self._request({
            "request_id": request_id, "operation": "ACK_REMINDER",
            "scheduled_task_id": scheduled_task_id, "idempotency_key": idempotency_key,
            "status": status, "ack_at": stamp, "error": error if status == "FAILED" else None,
            "statements": ack_statements(scheduled_task_id, idempotency_key, status,
                                         stamp, error if status == "FAILED" else None),
        }, attempts=MAX_ATTEMPTS)
