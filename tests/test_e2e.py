"""T11：WorkBuddy MCP -> Agent -> 受限后端 -> MySQL 集成验收。"""

import unittest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch
from zoneinfo import ZoneInfo

import db
import sql_executor
from agent import AgendaAgent
from app import app
from config import DB_BACKEND
from mcp import AgendaMCP


@unittest.skipUnless(DB_BACKEND == "mysql", "T11 需要已迁移的 MySQL")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.token = uuid4().hex
        self.todo_ids = []
        self.task_ids = []
        self.event_ids = []
        self.clock = lambda: datetime(2026, 10, 1, 9, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 1, 9, tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(tz)
        clock_patch = patch('sql_executor.datetime', FrozenDatetime)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.mcp = AgendaMCP(AgendaAgent(sql_executor.execute, clock=self.clock))

    def tearDown(self):
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                for event_id in self.event_ids:
                    cur.execute("DELETE FROM calendar_events WHERE id=%s", (event_id,))
                for task_id in self.task_ids:
                    cur.execute("DELETE FROM sent_reminders WHERE scheduled_task_id=%s", (task_id,))
                    cur.execute("DELETE FROM scheduled_tasks WHERE id=%s", (task_id,))
                for todo_id in self.todo_ids:
                    cur.execute("SELECT id FROM scheduled_tasks WHERE todo_id=%s", (todo_id,))
                    for row in cur.fetchall():
                        cur.execute("DELETE FROM sent_reminders WHERE scheduled_task_id=%s", (row["id"],))
                        cur.execute("DELETE FROM scheduled_tasks WHERE id=%s", (row["id"],))
                    cur.execute("DELETE FROM todos WHERE id=%s", (todo_id,))

    def _create_manual_occupancy(self, start_local, end_local):
        stamp = datetime(2026, 10, 1)
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO todos (title,created_at,updated_at,request_id) VALUES (%s,%s,%s,%s)",
                            (f"T11-{self.token}", stamp, stamp, f"occupy-{uuid4().hex}"))
                todo_id = cur.lastrowid
                cur.execute("INSERT INTO scheduled_tasks (todo_id,start_at,end_at,timezone,status,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                            (todo_id, start_local - timedelta(hours=8), end_local - timedelta(hours=8), "Asia/Shanghai", "ACTIVE", stamp))
                self.todo_ids.append(todo_id)
                self.task_ids.append(cur.lastrowid)

    def test_create_manual_and_legacy_routes(self):
        request_id = f"T11-{self.token}"
        result = self.mcp.call_tool("create_schedule", {"request_id": request_id, "text": "2040年10月2日下午三点准备资料一小时"})
        self.assertTrue(result["success"], result)
        self.todo_ids.append(result["schedule"]["todo_id"])
        self.task_ids.append(result["schedule"]["scheduled_task_id"])
        self.assertFalse(result["schedule"]["auto_scheduled"])
        self.assertEqual(result["schedule"]["timezone"], "Asia/Shanghai")
        replay = self.mcp.call_tool("create_schedule", {"request_id": request_id, "text": "2040年10月2日下午三点准备资料一小时"})
        self.assertTrue(replay["success"])
        self.assertEqual(replay.get("idempotent_replay"), True)

        client = app.test_client()
        legacy = client.post("/api/todo", json={"title": f"T11-legacy-{self.token}", "estimate_min": 30})
        self.assertEqual(legacy.status_code, 201)
        self.todo_ids.append(legacy.get_json()["todo_id"])
        self.assertEqual(client.get("/api/todos").status_code, 200)
        self.assertEqual(client.get("/api/schedule").status_code, 200)
        self.assertEqual(client.post("/api/reminder/scan").status_code, 200)

    def test_conflict_and_auto_schedule_avoid_occupancy(self):
        self._create_manual_occupancy(datetime(2026, 10, 2, 9), datetime(2026, 10, 2, 10))
        conflict = self.mcp.call_tool("create_schedule", {"request_id": f"conflict-{self.token}", "text": "2026年10月2日上午九点开会一小时"})
        self.assertFalse(conflict["success"])
        self.assertEqual(conflict["error"]["code"], "TIME_CONFLICT")
        auto = self.mcp.call_tool("create_schedule", {"request_id": f"auto-{self.token}", "text": "明天安排一小时写周报"})
        self.assertTrue(auto["success"], auto)
        self.todo_ids.append(auto["schedule"]["todo_id"])
        self.task_ids.append(auto["schedule"]["scheduled_task_id"])
        self.assertTrue(auto["schedule"]["auto_scheduled"])
        self.assertNotEqual(auto["schedule"]["start_at"], "2026-10-02 01:00:00")

    def test_auto_schedule_avoids_calendar_event(self):
        event_id = f"T11-event-{self.token}"
        self.event_ids.append(event_id)
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO calendar_events (id,type_id,title,event_date,start_time,end_time) VALUES (%s,%s,%s,%s,%s,%s)",
                            (event_id, "meeting", "T11 occupied", "2026-10-02", "09:00:00", "12:00:00"))
        auto = self.mcp.call_tool("create_schedule", {"request_id": f"calendar-{self.token}", "text": "明天安排一小时写周报"})
        self.assertTrue(auto["success"], auto)
        self.todo_ids.append(auto["schedule"]["todo_id"])
        self.task_ids.append(auto["schedule"]["scheduled_task_id"])
        self.assertNotIn(auto["schedule"]["start_at"], {"2026-10-02 01:00:00", "2026-10-02 02:00:00", "2026-10-02 03:00:00"})

    def test_batch_failure_rolls_back_previous_insert(self):
        request_id = f"rollback-{self.token}"
        payload = {
            "request_id": request_id, "operation": "SQL_BATCH", "statements": [
                {"sql": "INSERT INTO todos (title,created_at,updated_at,request_id) VALUES (%s,%s,%s,%s)",
                 "params": [f"T11 rollback {self.token}", "2026-10-01 00:00:00", "2026-10-01 00:00:00", request_id]},
                {"sql": "INSERT INTO todos (title,created_at,updated_at,request_id) VALUES (%s,%s,%s,%s)",
                 "params": [f"T11 duplicate {self.token}", "2026-10-01 00:00:00", "2026-10-01 00:00:00", request_id]},
            ],
        }
        response = sql_executor.execute(payload)
        self.assertFalse(response["success"])
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM todos WHERE request_id=%s", (request_id,))
                self.assertEqual(cur.fetchone()["n"], 0)

    def test_no_slot_and_retry_outcomes(self):
        class Backend:
            def __init__(self, responses): self.responses, self.calls = list(responses), []
            def __call__(self, payload):
                self.calls.append(payload)
                return self.responses.pop(0)

        no_slot_backend = Backend([{"success": True, "results": [{"rows": [{"event_date": "2026-10-02", "start_time": "00:00:00", "end_time": "23:59:59"}]}]}])
        no_slot = AgendaMCP(AgendaAgent(no_slot_backend, clock=self.clock)).call_tool(
            "create_schedule", {"request_id": "no-slot", "text": "明天安排一小时写周报"})
        self.assertFalse(no_slot["success"])
        self.assertEqual(no_slot["error"]["code"], "NO_AVAILABLE_SLOT")
        retry_backend = Backend([{"success": False, "retryable": True, "error": {"code": "TIME_CONFLICT"}}, {"success": True}])
        retry = AgendaMCP(AgendaAgent(retry_backend)).call_tool("poll_reminders", {"request_id": "retry"})
        self.assertTrue(retry["success"])
        self.assertEqual(len(retry_backend.calls), 2)
        fail_backend = Backend([{"success": False, "retryable": True, "error": {"code": "TIME_CONFLICT"}}] * 3)
        failed = AgendaMCP(AgendaAgent(fail_backend)).call_tool("poll_reminders", {"request_id": "failed"})
        self.assertFalse(failed["success"])
        self.assertEqual(len(fail_backend.calls), 3)

    def test_reminder_poll_ack_retry_and_duplicate(self):
        result = self.mcp.call_tool("create_schedule", {"request_id": f"rem-{self.token}", "text": "2026年10月1日上午十点提醒我开会"})
        self.assertTrue(result["success"], result)
        task_id = result["schedule"]["scheduled_task_id"]
        todo_id = result["schedule"]["todo_id"]
        self.todo_ids.append(todo_id); self.task_ids.append(task_id)
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE scheduled_tasks SET reminder_at=%s WHERE id=%s", (datetime(2026, 10, 1, 1), task_id))
        polled = self.mcp.call_tool("poll_reminders", {"request_id": f"poll-{self.token}", "now": "2026-10-01T09:00:00+08:00"})
        self.assertTrue(polled["success"], polled)
        key = next(item["reminder_idempotency_key"] for item in polled["reminders"] if item["scheduled_task_id"] == task_id)
        failed = self.mcp.call_tool("ack_reminder", {"request_id": f"ack-f-{self.token}", "scheduled_task_id": task_id, "idempotency_key": key, "status": "FAILED", "error": "通知失败"})
        self.assertTrue(failed["success"], failed)
        polled_again = self.mcp.call_tool("poll_reminders", {"request_id": f"poll-2-{self.token}", "now": "2026-10-01T09:00:00+08:00"})
        self.assertTrue(any(item["scheduled_task_id"] == task_id for item in polled_again["reminders"]))
        sent = self.mcp.call_tool("ack_reminder", {"request_id": f"ack-s-{self.token}", "scheduled_task_id": task_id, "idempotency_key": key})
        duplicate = self.mcp.call_tool("ack_reminder", {"request_id": f"ack-s2-{self.token}", "scheduled_task_id": task_id, "idempotency_key": key})
        self.assertTrue(sent["success"] and duplicate["success"])
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM sent_reminders WHERE scheduled_task_id=%s", (task_id,))
                self.assertEqual(cur.fetchone()["n"], 1)


if __name__ == "__main__":
    unittest.main()
