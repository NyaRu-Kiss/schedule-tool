import threading
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests
from werkzeug.serving import make_server

import sql_executor
from agent import AgendaAgent
from app import app


class FixedIntentParser:
    def parse(self, text, *, timezone, today):
        return {
            "title": "写周报",
            "date": "2040-10-10",
            "start_time": None,
            "duration_min": 60,
            "reminder_requested": False,
            "reminder_minutes": None,
            "timezone": timezone,
            "needs_clarification": False,
            "clarification_question": None,
        }


class R04RetryProtocolTests(unittest.TestCase):
    def test_http_requests_count_logical_rounds_and_preserve_error_protocol(self):
        server = make_server("127.0.0.1", 0, app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/api/internal/sql/execute"
        received = []
        responses = []

        def execute(payload):
            received.append((payload["operation"], payload["attempt"]))
            if payload["operation"] == "FIND_AVAILABLE_SLOTS":
                return {
                    "success": True,
                    "request_id": payload["request_id"],
                    "attempt": payload["attempt"],
                    "results": [{"rows": []}, {"rows": []}],
                }
            if payload["attempt"] == 1:
                return sql_executor.make_error_response(
                    payload["request_id"], payload["attempt"], "TIME_CONFLICT", "档期冲突"
                )
            return {"success": True, "request_id": payload["request_id"],
                    "attempt": payload["attempt"], "schedule": {"auto_scheduled": 1}}

        def backend(payload):
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": "Bearer r04-test-token"},
                timeout=5,
            )
            responses.append(response.json())
            return response.json()

        try:
            with patch("app.INTERNAL_SERVICE_TOKEN", "r04-test-token"), \
                    patch.object(sql_executor, "execute", side_effect=execute):
                agent = AgendaAgent(
                    backend,
                    timezone="Asia/Shanghai",
                    clock=lambda: datetime(2040, 10, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
                    intent_parser=FixedIntentParser(),
                )
                result = agent.create_schedule("明天安排一小时写周报", "r04-http-rounds")
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

        self.assertFalse(worker.is_alive())
        self.assertTrue(result["success"], result)
        self.assertEqual(received, [
            ("FIND_AVAILABLE_SLOTS", 1),
            ("AUTO_CREATE_SCHEDULE", 1),
            ("FIND_AVAILABLE_SLOTS", 2),
            ("AUTO_CREATE_SCHEDULE", 2),
        ])
        conflict = responses[1]
        self.assertTrue(conflict["retryable"])
        self.assertEqual(set(conflict), {"success", "request_id", "attempt", "retryable", "error"})
        self.assertEqual(set(conflict["error"]), {"code", "message"})
        self.assertNotIn("retryable", conflict["error"])


if __name__ == "__main__":
    unittest.main()
