"""
日程效率工具 - Flask HTTP 接口

POST /api/todo           添加待办
GET  /api/todos          查询待办列表
GET  /api/schedule       查看档期排期
POST /api/schedule/run   手动触发编排
POST /api/todo/<id>/done 标记完成
POST /api/reminder/scan  手动触发提醒扫描
GET  /api/webhook/config 查看 webhook 配置
POST /api/webhook/test  发送测试消息验证推送
GET  /api/webhook/logs   查看推送日志

未来 WorkBuddy/ADP 接入时，其连接器直接调用这些 endpoint 即可。
"""

import logging
import hmac
from datetime import datetime
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request, send_from_directory

import db
import scheduler
import sql_executor
from config import INTERNAL_SERVICE_TOKEN, REMIND_LEAD_MINUTES, get_webhook_config
from scanner import start_scan_thread
from remind import scan_and_remind, push

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("app")

app = Flask(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent
DESKTOP_DIST = ROOT_DIR / 'schedule-planner' / 'schedule-planner' / 'dist'
MOBILE_DIST = ROOT_DIR / 'schedule-planner' / 'schedule-planner-mobile' / 'dist'
_db_ready = False
_db_lock = Lock()


@app.post("/api/internal/sql/execute")
def execute_agent_sql():
    """执行 Agent 提交的受限参数化 SQL 批次。"""
    payload = request.get_json(silent=True)
    response = sql_executor.execute(payload)
    status = sql_executor.http_status_for(response)
    # HTTP 状态不放入业务错误 JSON，避免暴露实现细节；仅使用稳定错误码。
    return jsonify(response), status


def _service_auth_response():
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {INTERNAL_SERVICE_TOKEN}" if INTERNAL_SERVICE_TOKEN else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        sql_executor.audit_event("authentication_failed", phase="service_auth",
                                 code="PERMISSION_DENIED")
        response = sql_executor.make_error_response(
            None, 1, "PERMISSION_DENIED", "需要有效的 Agent 服务认证"
        )
        return jsonify(response), sql_executor.http_status_for(response)
    return None


@app.before_request
def _ensure_db():
    global _db_ready
    if request.path == "/api/internal/sql/execute":
        auth_error = _service_auth_response()
        if auth_error:
            return auth_error
    if request.path == "/api/internal/sql/execute":
        return None
    if request.path.startswith('/api/') and not _db_ready:
        with _db_lock:
            if not _db_ready:
                db.init_db()
                _db_ready = True


# ---------- 待办 CRUD ----------

@app.post("/api/todo")
def add_todo():
    """
    Body:
      title (str, 必填)
      priority (1|2|3, 默认 2)
      deadline (ISO 时间, 可选, 如 "2026-10-08T18:00" 或 "2026-10-08 18:00")
      estimate_min (int, 可选)
      source (str, 默认 "api")
      raw_input (str, 可选)
    """
    data = request.get_json(force=True, silent=True) or request.form.to_dict()
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400

    priority = int(data.get("priority", 2))
    if priority not in (1, 2, 3):
        return jsonify(error="priority must be 1/2/3"), 400

    deadline_raw = (data.get("deadline") or "").strip() or None
    deadline = None
    if deadline_raw:
        try:
            deadline = deadline_raw.replace(" ", "T")
            datetime.fromisoformat(deadline)
        except ValueError:
            return jsonify(error="deadline format invalid, use YYYY-MM-DDTHH:MM"), 400

    estimate_min = data.get("estimate_min")
    if estimate_min is not None:
        estimate_min = int(estimate_min)

    source = data.get("source", "api")
    raw_input = data.get("raw_input")

    todo_id = db.insert_todo(
        title=title, priority=priority, deadline=deadline,
        estimate_min=estimate_min, source=source, raw_input=raw_input,
    )

    # 添加完立即尝试编排这一条，让用户看到即时排期
    result = scheduler.schedule_all()

    return jsonify({
        "todo_id": todo_id,
        "scheduled": result["scheduled"],
        "warnings": result["warnings"],
    }), 201


@app.get("/api/todos")
def get_todos():
    only_undone = request.args.get("undone") == "1"
    return jsonify(db.list_todos(only_undone=only_undone))


@app.post("/api/todo/<int:todo_id>/done")
def done_todo(todo_id):
    db.mark_todo_done(todo_id)
    return jsonify(ok=True)


# ---------- 档期 ----------

@app.get("/api/schedule")
def get_schedule():
    days = int(request.args.get("days", 3))
    return jsonify(db.list_schedule(days=days))


@app.post("/api/schedule/run")
def run_schedule():
    result = scheduler.schedule_all()
    return jsonify(result)


# ---------- 提醒 ----------

@app.post("/api/reminder/scan")
def manual_scan():
    n = scan_and_remind()
    return jsonify(reminded=n, lead_minutes=REMIND_LEAD_MINUTES)


# ---------- Webhook ----------

@app.get("/api/webhook/config")
def webhook_config():
    """查看当前 webhook 配置"""
    return jsonify(get_webhook_config())


@app.post("/api/webhook/test")
def webhook_test():
    """
    发送一条测试消息验证推送链路。
    Body 可选:
      message (str) — 自定义测试消息内容
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "🧪 测试消息：日程效率工具 webhook 推送验证成功")
    result = push(message, [], event_type="test")
    return jsonify({
        "success": result["success"],
        "status_code": result["status_code"],
        "error": result["error"],
        "retry_count": result["retry_count"],
        "duration_ms": result["duration_ms"],
        "log_id": result["log_id"],
    })


@app.get("/api/webhook/logs")
def webhook_logs():
    """查看推送日志"""
    limit = int(request.args.get("limit", 20))
    return jsonify(db.list_webhook_logs(limit=limit))


@app.get("/api/health")
def health():
    return jsonify(ok=True, time=datetime.now().isoformat())


# ---------- Calendar UI compatibility ----------

@app.get("/api/event-types")
def get_event_types():
    return jsonify(db.list_event_types())


@app.post("/api/event-types")
def create_event_type():
    data = request.get_json(force=True) or {}
    if not data.get("id") or not data.get("name") or not data.get("color"):
        return jsonify(error="id, name, color 均为必填"), 400
    try:
        return jsonify(db.create_event_type(data["id"], data["name"], data["color"])), 201
    except Exception as exc:
        return jsonify(error=str(exc)), 409


@app.put("/api/event-types/<event_id>")
def update_event_type(event_id):
    data = request.get_json(force=True) or {}
    result = db.update_event_type(event_id, data.get("name"), data.get("color"))
    return jsonify(result) if result else (jsonify(error="未找到该事件类型"), 404)


@app.delete("/api/event-types/<event_id>")
def delete_event_type(event_id):
    if not db.delete_event_type(event_id):
        return jsonify(error="该类型正被日程使用，无法删除"), 409
    return "", 204


@app.get("/api/events")
def get_events():
    return jsonify(db.list_calendar_events())


@app.post("/api/events")
def create_event():
    data = request.get_json(force=True) or {}
    required = ("id", "typeId", "title", "date", "startTime", "endTime")
    if any(not data.get(key) for key in required):
        return jsonify(error="缺少必填字段"), 400
    if str(data['id']).startswith('todo-'):
        return jsonify(error="该 ID 为自动排期待办保留"), 400
    try:
        return jsonify(db.create_calendar_event(data)), 201
    except Exception as exc:
        return jsonify(error=str(exc)), 409


@app.put("/api/events/<event_id>")
def update_event(event_id):
    data = request.get_json(force=True) or {}
    result = db.update_calendar_event(event_id, data)
    return jsonify(result) if result else (jsonify(error="未找到该日程"), 404)


@app.delete("/api/events/<event_id>")
def delete_event(event_id):
    if not db.delete_calendar_event(event_id):
        return jsonify(error="自动排期待办请通过待办接口操作"), 409
    return "", 204


@app.get("/api/goals")
def get_goals():
    return jsonify(db.list_goals())


@app.post("/api/goals")
def create_goal():
    data = request.get_json(force=True) or {}
    if any(not data.get(key) for key in ("id", "title", "startDate", "endDate")):
        return jsonify(error="缺少必填字段"), 400
    return jsonify(db.save_goal(data)), 201


@app.put("/api/goals/<goal_id>")
def update_goal(goal_id):
    data = request.get_json(force=True) or {}
    if not any(goal['id'] == goal_id for goal in db.list_goals()):
        return jsonify(error="未找到该目标"), 404
    data["id"] = goal_id
    return jsonify(db.save_goal(data))


@app.delete("/api/goals/<goal_id>")
def delete_goal(goal_id):
    db.delete_goal(goal_id)
    return "", 204


@app.patch("/api/goals/<goal_id>/milestones/<milestone_id>")
def update_milestone(goal_id, milestone_id):
    data = request.get_json(force=True) or {}
    goals = db.list_goals()
    goal = next((item for item in goals if item["id"] == goal_id), None)
    if not goal:
        return jsonify(error="未找到该目标"), 404
    for milestone in goal["milestones"]:
        if milestone["id"] == milestone_id:
            milestone["completed"] = bool(data.get("completed"))
            db.save_goal(goal)
            return "", 204
    return jsonify(error="未找到该里程碑"), 404


@app.get('/mobile')
@app.get('/mobile/<path:asset>')
def mobile_ui(asset=''):
    file_path = MOBILE_DIST / asset
    return send_from_directory(MOBILE_DIST, asset if asset and file_path.is_file() else 'index.html')


@app.get('/')
@app.get('/<path:asset>')
def desktop_ui(asset=''):
    file_path = DESKTOP_DIST / asset
    return send_from_directory(DESKTOP_DIST, asset if asset and file_path.is_file() else 'index.html')


# ---------- 入口 ----------

def main():
    db.init_db()
    start_scan_thread()
    from config import HOST, PORT
    log.info("启动服务 %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
