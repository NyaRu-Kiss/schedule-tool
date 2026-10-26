"""T08 验收：Agent -> 后端受限 SQL 执行器 -> 已迁移的 MySQL。

运行：python -m unittest discover -s tests -v
仅创建本次测试的隔离记录，并在 finally 中删除，不启动 HTTP/扫描服务。
"""

import unittest
from datetime import datetime
from uuid import uuid4

import db
import sql_executor
from agent import AgendaAgent
from config import DB_BACKEND


@unittest.skipUnless(DB_BACKEND == "mysql", "需要已迁移的 MySQL 测试数据库")
class ReminderQueryTests(unittest.TestCase):
    def test_ack_sent_is_idempotent_transaction_batch(self):
        calls = []

        def backend(payload):
            calls.append(payload)
            return {"success": True, "results": []}

        agent = AgendaAgent(backend, clock=lambda: datetime(2001, 1, 1))
        result = agent.ack_reminder("ack-1", 7, "reminder:7")
        self.assertTrue(result["success"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["operation"], "ACK_REMINDER")
        self.assertEqual(len(calls[0]["statements"]), 2)
        self.assertIn("sent_reminders", calls[0]["statements"][1]["sql"])

    def test_ack_failed_only_updates_and_can_be_retried(self):
        calls = []

        def backend(payload):
            calls.append(payload)
            return {"success": True, "results": []}

        agent = AgendaAgent(backend, clock=lambda: datetime(2001, 1, 1))
        self.assertTrue(agent.ack_reminder("ack-2", 8, "reminder:8", status="FAILED",
                                           error="通知服务不可用")["success"])
        self.assertEqual(len(calls[0]["statements"]), 1)
        self.assertNotIn("sent_reminders", calls[0]["statements"][0]["sql"])
        self.assertTrue(agent.ack_reminder("ack-3", 8, "reminder:8")["success"])
        self.assertEqual(len(calls[1]["statements"]), 2)

    def test_ack_invalid_arguments_do_not_call_backend(self):
        def forbidden_call(payload):
            self.fail("非法确认不应调用后端")

        agent = AgendaAgent(forbidden_call)
        for kwargs in ({"scheduled_task_id": 0, "idempotency_key": "k"},
                       {"scheduled_task_id": 1, "idempotency_key": "k", "status": "BAD"},
                       {"scheduled_task_id": 1, "idempotency_key": "k", "status": "FAILED", "error": "x" * 1001}):
            result = agent.ack_reminder("bad-ack", **kwargs)
            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")

    def test_ack_backend_requires_consistent_batch_and_key(self):
        from sql_executor import ExecutorError, _validate_request
        from reminder_sql import ack_statements

        statements = ack_statements(9, "reminder:9", "SENT", "2001-01-01 00:00:00")
        payload = {"request_id": "ack-validate", "operation": "ACK_REMINDER",
                   "scheduled_task_id": 9, "idempotency_key": "reminder:9",
                   "status": "SENT", "statements": statements}
        _validate_request(payload)

        bad_key = dict(payload, idempotency_key="different")
        with self.assertRaises(ExecutorError):
            _validate_request(bad_key)
        bad_batch = dict(payload, statements=statements[:1])
        with self.assertRaises(ExecutorError):
            _validate_request(bad_batch)
    def test_due_filters_and_fresh_poll(self):
        token = uuid4().hex
        todo_ids = []
        task_ids = []
        agent = AgendaAgent(sql_executor.execute)
        stamp = datetime(2001, 1, 1)

        def add_case(name, *, reminder_status="PENDING", sent=0, done=0,
                     status="ACTIVE", todo_done=0, reminder_at=stamp, key=None):
            with db.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO todos (title,done,created_at,updated_at) VALUES (%s,%s,%s,%s)",
                        (f"T08-{token}-{name}", todo_done, stamp, stamp),
                    )
                    todo_id = cursor.lastrowid
                    todo_ids.append(todo_id)
                    cursor.execute(
                        "INSERT INTO scheduled_tasks "
                        "(todo_id,start_at,end_at,created_at,reminder_at,reminder_status,"
                        "reminder_sent,done,status,reminder_idempotency_key) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (todo_id, stamp, datetime(2001, 1, 1, 1), stamp, reminder_at,
                         reminder_status, sent, done, status, key),
                    )
                    task_ids.append(cursor.lastrowid)
                    return cursor.lastrowid

        try:
            due = add_case("due", key=f"T08-{token}")
            no_key = add_case("null-key")
            add_case("future", reminder_at=datetime(2001, 1, 2))
            add_case("no-reminder", reminder_at=None)
            add_case("sent", reminder_status="SENT", sent=1)
            add_case("legacy-sent", sent=1)
            add_case("done", done=1)
            add_case("todo-done", todo_done=1)
            add_case("cancelled", status="CANCELLED")
            add_case("completed", status="COMPLETED")

            def poll():
                # 刻意复用 ID：轮询不能重放发送确认之前的旧查询缓存。
                response = agent.poll_reminders(
                    f"T08-{token}", now="2001-01-01T08:00:00+08:00"
                )
                self.assertTrue(response["success"], response)
                return {r["scheduled_task_id"]: r for r in response["reminders"]}

            rows = poll()
            self.assertEqual(set(rows).intersection(task_ids), {due, no_key})
            self.assertEqual(rows[due]["reminder_idempotency_key"], f"T08-{token}")
            self.assertEqual(rows[no_key]["reminder_idempotency_key"], f"reminder:{no_key}")
            for field in ("title", "start_at", "end_at", "reminder_at", "timezone"):
                self.assertIn(field, rows[due])
            for field in ("start_at", "end_at", "reminder_at"):
                self.assertIsInstance(rows[due][field], str)
                self.assertNotIn("GMT", rows[due][field])
                self.assertRegex(rows[due][field], r"^\d{4}-\d{2}-\d{2} ")

            with db.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE scheduled_tasks SET reminder_status=%s,reminder_sent=%s WHERE id IN (%s,%s)",
                        ("SENT", 1, due, no_key),
                    )
            self.assertFalse(set(poll()).intersection(task_ids))
            empty = agent.poll_reminders(f"empty-{token}", now="1000-01-01T00:00:00Z")
            self.assertTrue(empty["success"], empty)
            self.assertEqual(empty["reminders"], [])
        finally:
            with db.get_conn() as conn:
                with conn.cursor() as cursor:
                    for task_id in task_ids:
                        cursor.execute("DELETE FROM scheduled_tasks WHERE id=%s", (task_id,))
                    for todo_id in todo_ids:
                        cursor.execute("DELETE FROM todos WHERE id=%s", (todo_id,))

    def test_invalid_arguments_do_not_call_backend(self):
        def forbidden_call(payload):
            self.fail("非法参数不应调用后端")

        agent = AgendaAgent(forbidden_call)
        for arguments in ({"limit": 0}, {"limit": True}, {"now": "bad-time"}):
            result = agent.poll_reminders("invalid-poll", **arguments)
            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
