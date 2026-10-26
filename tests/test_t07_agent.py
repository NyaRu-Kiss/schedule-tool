import unittest
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from agent import AgendaAgent
import config
import db
import sql_executor
from app import app


class T07AgentTests(unittest.TestCase):
    def intent(self, **changes):
        intent = {
            "title": "写周报", "date": "2040-10-10", "start_time": "15:00",
            "duration_min": 60, "reminder_requested": True, "reminder_minutes": 10,
            "timezone": "Asia/Shanghai", "needs_clarification": False,
            "clarification_question": None,
        }
        intent.update(changes)
        return intent

    def test_structured_intent_creates_parameterized_manual_schedule(self):
        parser = Mock()
        parser.parse.return_value = self.intent()
        backend = Mock(return_value={"success": True})
        result = AgendaAgent(backend, intent_parser=parser,
                             clock=lambda: datetime(2040, 10, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai")))\
            .create_schedule("下周三下午三点提醒我写周报", "t07-manual")
        self.assertTrue(result["success"])
        parser.parse.assert_called_once_with("下周三下午三点提醒我写周报",
                                             timezone="Asia/Shanghai", today=datetime(2040, 10, 9).date())
        payload = backend.call_args.args[0]
        self.assertEqual(payload["operation"], "CREATE_SCHEDULE")
        sql = payload["statements"][0]["sql"]
        params = payload["statements"][0]["params"]
        self.assertIn("VALUES (%s", sql)
        self.assertEqual(params[0], "写周报")
        self.assertEqual(params[2], 60)
        self.assertEqual(params[4], "下周三下午三点提醒我写周报")
        self.assertEqual(payload["statements"][1]["params"][1:3],
                         ["2040-10-10 07:00:00", "2040-10-10 08:00:00"])
        self.assertEqual(payload["statements"][1]["params"][5], "2040-10-10 06:50:00")

    def test_missing_duration_defaults_and_unspecified_start_uses_auto_schedule(self):
        parser = Mock()
        parser.parse.return_value = self.intent(start_time=None, duration_min=None,
                                                reminder_requested=False, reminder_minutes=None)
        calls = []
        def backend(payload):
            calls.append(payload)
            if payload["operation"] == "FIND_AVAILABLE_SLOTS":
                return {"success": True, "results": [{"rows": []}, {"rows": []}]}
            return {"success": True}

        result = AgendaAgent(backend, intent_parser=parser,
                             clock=lambda: datetime(2040, 10, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai")))\
            .create_schedule("明天写周报", "t07-auto")
        self.assertTrue(result["success"])
        self.assertEqual([call["operation"] for call in calls], ["FIND_AVAILABLE_SLOTS", "AUTO_CREATE_SCHEDULE"])
        self.assertEqual(calls[0]["duration_min"], 30)
        self.assertEqual(calls[1]["statements"][0]["params"][2], 30)
        parser.parse.assert_called_once()

    def test_ambiguity_returns_question_without_backend_call(self):
        parser = Mock()
        parser.parse.return_value = self.intent(needs_clarification=True,
                                                clarification_question="你希望安排在哪一天？")
        backend = Mock()
        result = AgendaAgent(backend, intent_parser=parser).create_schedule("安排一下", "t07-ask")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NEEDS_CLARIFICATION")
        self.assertEqual(result["clarification_question"], "你希望安排在哪一天？")
        backend.assert_not_called()

    def test_invalid_intent_and_parser_error_never_reach_backend(self):
        for intent in (self.intent(title=" "), self.intent(timezone="Bad/Zone"),
                       self.intent(reminder_requested=False, reminder_minutes=5)):
            with self.subTest(intent=intent):
                parser = Mock()
                parser.parse.return_value = intent
                backend = Mock()
                result = AgendaAgent(backend, intent_parser=parser).create_schedule("input", "t07-invalid")
                self.assertFalse(result["success"])
                self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")
                backend.assert_not_called()

        parser = Mock()
        parser.parse.side_effect = RuntimeError("model response must not escape")
        backend = Mock()
        result = AgendaAgent(backend, intent_parser=parser).create_schedule("input", "t07-model-error")
        self.assertEqual(result["error"]["code"], "INTENT_PARSE_FAILED")
        self.assertNotIn("model response", result["error"]["message"])
        backend.assert_not_called()

    def test_explicit_timezone_from_text_is_used_unless_caller_overrides_it(self):
        parser = Mock()
        parser.parse.return_value = self.intent(timezone="America/Los_Angeles")
        backend = Mock(return_value={"success": True})
        agent = AgendaAgent(backend, intent_parser=parser,
                            clock=lambda: datetime(2040, 10, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai")))
        result = agent.create_schedule("洛杉矶时间下午三点开会", "t07-zone")
        self.assertTrue(result["success"])
        self.assertEqual(backend.call_args.args[0]["statements"][0]["params"][5], "America/Los_Angeles")
        backend.reset_mock()
        result = agent.create_schedule("洛杉矶时间下午三点开会", "t07-zone-override", timezone="Asia/Tokyo")
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")
        backend.assert_not_called()


@unittest.skipUnless(config.DB_BACKEND == "mysql", "真实联调需要已迁移的 MySQL")
class T07IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.prefix = "T07-" + uuid4().hex
        self.requests = []
        self.models = []
        test_case = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                size = int(self.headers["Content-Length"])
                request = json.loads(self.rfile.read(size))
                test_case.models.append((request["model"], self.headers.get("Authorization")))
                user = json.loads(request["messages"][1]["content"])
                target_date = "2040-10-11" if request["model"].endswith("a") else "2040-10-12"
                response = {"choices": [{"message": {"content": json.dumps({
                    "title": user["text"], "date": target_date, "start_time": "15:00",
                    "duration_min": 45, "reminder_requested": False, "reminder_minutes": None,
                    "timezone": user["timezone"], "needs_clarification": False,
                    "clarification_question": None,
                })}}]}
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.llm_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.llm_thread = threading.Thread(target=self.llm_server.serve_forever, daemon=True)
        self.llm_thread.start()
        self.addCleanup(self.close_llm_server)
        self.auth = patch("app.INTERNAL_SERVICE_TOKEN", "t07-token")
        self.auth.start()
        self.addCleanup(self.auth.stop)
        self.executor_clock = patch("sql_executor.datetime", type("FrozenDatetime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2040, 10, 9, 8, tzinfo=tz))}))
        self.executor_clock.start()
        self.addCleanup(self.executor_clock.stop)

    def close_llm_server(self):
        self.llm_server.shutdown()
        self.llm_server.server_close()
        self.llm_thread.join(timeout=5)

    def tearDown(self):
        with db.get_conn() as conn, conn.cursor() as cursor:
            for request_id in self.requests:
                cursor.execute("DELETE r FROM sent_reminders r JOIN scheduled_tasks s ON s.id=r.scheduled_task_id "
                               "JOIN todos t ON t.id=s.todo_id WHERE t.request_id=%s", (request_id,))
                cursor.execute("DELETE s FROM scheduled_tasks s JOIN todos t ON t.id=s.todo_id "
                               "WHERE t.request_id=%s", (request_id,))
                cursor.execute("DELETE FROM todos WHERE request_id=%s", (request_id,))
                sql_executor._cache.pop(request_id, None)

    def test_real_http_llm_config_replacement_and_authenticated_parameterized_backend(self):
        endpoint = f"http://127.0.0.1:{self.llm_server.server_port}/v1"
        backend_payloads = []

        def backend(payload):
            backend_payloads.append(payload)
            with app.test_client() as client:
                return client.post("/api/internal/sql/execute", json=payload,
                                   headers={"Authorization": "Bearer t07-token"}).get_json()

        results = []
        for model in ("deployment-model-a", "deployment-model-b"):
            request_id = f"{self.prefix}-{model[-1]}"
            self.requests.append(request_id)
            env = {"SCHEDULE_LLM_BASE_URL": endpoint, "SCHEDULE_LLM_MODEL": model,
                   "SCHEDULE_LLM_API_KEY": "integration-key", "SCHEDULE_LLM_TIMEOUT": "5"}
            with patch.dict("os.environ", env):
                agent = AgendaAgent(backend, clock=lambda: datetime(
                    2040, 10, 9, 8, tzinfo=ZoneInfo("Asia/Shanghai")))
                results.append(agent.create_schedule(f"集成任务 {model}", request_id))

        self.assertTrue(all(result["success"] for result in results), results)
        self.assertEqual(self.models, [("deployment-model-a", "Bearer integration-key"),
                                       ("deployment-model-b", "Bearer integration-key")])
        self.assertEqual(len(backend_payloads), 2)
        for payload in backend_payloads:
            self.assertEqual(payload["operation"], "CREATE_SCHEDULE")
            self.assertEqual(payload["max_attempts"], 3)
            self.assertEqual(len(payload["statements"]), 2)
            self.assertTrue(all("%s" in statement["sql"] for statement in payload["statements"]))
            self.assertTrue(all(isinstance(statement["params"], list) for statement in payload["statements"]))
        self.assertEqual([result["schedule"]["start_at"] for result in results],
                         ["2040-10-11 07:00:00", "2040-10-12 07:00:00"])
        unauthorized_id = f"{self.prefix}-unauthorized"
        payload = dict(backend_payloads[0], request_id=unauthorized_id)
        payload["statements"] = [dict(statement, params=list(statement["params"]))
                                  for statement in payload["statements"]]
        payload["statements"][0]["params"][6] = unauthorized_id
        with app.test_client() as client:
            response = client.post("/api/internal/sql/execute", json=payload)
        self.assertEqual(response.status_code, 403)
        with db.get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM todos WHERE request_id=%s", (unauthorized_id,))
            self.assertEqual(cursor.fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()
