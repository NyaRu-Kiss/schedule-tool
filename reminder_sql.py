"""提醒确认的参数化 SQL 契约；不访问数据库。"""


def ack_statements(task_id, key, status, stamp, error=None):
    statements = [{
        "sql": (
            "UPDATE scheduled_tasks SET reminder_status=%s,reminder_sent=%s,"
            "reminder_idempotency_key=%s,reminder_attempt_count=reminder_attempt_count+%s,"
            "reminder_last_attempt_at=%s,reminder_error=%s WHERE id=%s"
        ),
        "params": [status, int(status == "SENT"), key, 1, stamp, error, task_id],
    }]
    if status == "SENT":
        statements.append({
            "sql": "INSERT INTO sent_reminders (scheduled_task_id,sent_at,idempotency_key) VALUES (%s,%s,%s)",
            "params": [task_id, stamp, key],
        })
    return statements
