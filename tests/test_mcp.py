import io
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator
from werkzeug.serving import make_server

from app import app
from mcp import AgendaMCP, serve_stdio
from mcp_runtime import build_server


class FakeAgent:
    def __init__(self):
        self.calls = []

    def create_schedule(self, text, request_id, *, timezone=None):
        self.calls.append(("create_schedule", text, request_id, timezone))
        return {"success": True, "kind": "create"}

    def poll_reminders(self, request_id, *, now=None, limit=100):
        self.calls.append(("poll_reminders", request_id, now, limit))
        return {"success": True, "kind": "poll"}

    def ack_reminder(self, request_id, task_id, key, *, status="SENT", error=None, now=None):
        self.calls.append(("ack_reminder", request_id, task_id, key, status, error, now))
        return {"success": True, "kind": "ack"}


class MCPTests(unittest.TestCase):
    def test_tools_forward_and透传(self):
        agent = FakeAgent()
        mcp = AgendaMCP(agent)
        self.assertEqual(mcp.call_tool("create_schedule", {"text": "x", "request_id": "r"}), {"success": True, "kind": "create"})
        self.assertEqual(mcp.call_tool("poll_reminders", {"request_id": "r", "limit": 3}), {"success": True, "kind": "poll"})
        self.assertEqual(mcp.call_tool("ack_reminder", {"request_id": "r", "scheduled_task_id": 1, "idempotency_key": "k"}), {"success": True, "kind": "ack"})
        self.assertEqual([call[0] for call in agent.calls], ["create_schedule", "poll_reminders", "ack_reminder"])

    def test_stdio_rpc_round_trip(self):
        agent = FakeAgent()
        incoming = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                            "params": {"name": "poll_reminders", "arguments": {"request_id": "r"}}}) + "\n")
        output = io.StringIO()
        serve_stdio(AgendaMCP(agent), input_stream=incoming, output_stream=output)
        response = json.loads(output.getvalue())
        self.assertEqual(response["id"], 1)
        content = response["result"]["content"][0]
        self.assertEqual(content["type"], "text")
        self.assertEqual(json.loads(content["text"]), {"success": True, "kind": "poll"})
        self.assertNotIn("structuredContent", response["result"])

    def test_unknown_tool_is_rejected(self):
        result = AgendaMCP(FakeAgent()).call_tool("unknown", {})
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")

    def rpc(self, server, method, params=None, request_id=1):
        return server.handle_rpc({"jsonrpc": "2.0", "id": request_id,
                                  "method": method, "params": params or {}})

    def test_version_negotiation_and_content(self):
        for version in AgendaMCP.PROTOCOL_VERSIONS + ("2099-01-01",):
            with self.subTest(version=version):
                server = AgendaMCP(FakeAgent())
                expected = version if version in server.PROTOCOL_VERSIONS else server.PROTOCOL_VERSIONS[0]
                init = self.rpc(server, "initialize", {"protocolVersion": version,
                                "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
                self.assertEqual(init["result"]["protocolVersion"], expected)
                result = self.rpc(server, "tools/call", {"name": "poll_reminders",
                                  "arguments": {"request_id": "r"}})["result"]
                self.assertEqual(json.loads(result["content"][0]["text"])["kind"], "poll")
                self.assertFalse(result["isError"])
                self.assertEqual("structuredContent" in result, expected >= "2025-06-18")

    def test_notification_silence_and_stream_recovery(self):
        agent = FakeAgent()
        messages = [
            {"jsonrpc": "2.0", "id": "init", "method": "initialize",
             "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 9}},
            {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "poll_reminders", "arguments": {"request_id": "r"}}},
            [],
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": []},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
        ]
        incoming = io.StringIO("{bad json\n" + "\n".join(json.dumps(m) for m in messages) + "\n")
        output = io.StringIO()
        serve_stdio(AgendaMCP(agent), input_stream=incoming, output_stream=output)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in replies], [None, "init", None, 3, 4])
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[2]["error"]["code"], -32600)
        self.assertEqual(replies[3]["error"]["code"], -32602)
        self.assertEqual(replies[4]["result"], {})
        self.assertEqual(agent.calls, [])

    def test_schemas_are_complete_and_valid(self):
        tools = self.rpc(AgendaMCP(FakeAgent()), "tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], list(AgendaMCP.TOOL_NAMES))
        for tool in tools:
            schema = tool["inputSchema"]
            Draft202012Validator.check_schema(schema)
            self.assertTrue(set(schema["required"]) <= set(schema["properties"]))

    def test_invalid_arguments_do_not_reach_agent(self):
        agent = FakeAgent()
        server = AgendaMCP(agent)
        for name, arguments in [
            ("create_schedule", {}), ("create_schedule", {"text": "x", "request_id": 1}),
            ("create_schedule", {"text": "x", "request_id": "r", "timezone": "invalid/zone"}),
            ("poll_reminders", None), ("poll_reminders", []),
            ("poll_reminders", {"request_id": "r", "limit": True}),
            ("poll_reminders", {"request_id": "r", "limit": 101}),
            ("poll_reminders", {"request_id": "r", "extra": 1}),
            ("ack_reminder", {"request_id": "r", "scheduled_task_id": 0, "idempotency_key": "k"}),
            ("ack_reminder", {"request_id": "r", "scheduled_task_id": 1, "idempotency_key": "k", "status": "BAD"}),
        ]:
            with self.subTest(name=name, arguments=arguments):
                result = self.rpc(server, "tools/call", {"name": name, "arguments": arguments})["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(json.loads(result["content"][0]["text"])["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(agent.calls, [])

    def test_request_errors_keep_id(self):
        server = AgendaMCP(FakeAgent())
        for method, params, code in [("unknown", {}, -32601), ("initialize", {}, -32602),
                                     ("tools/call", {}, -32602)]:
            result = self.rpc(server, method, params, "r")
            self.assertEqual(result["id"], "r")
            self.assertEqual(result["error"]["code"], code)
        for invalid in [None, [], 1, {"id": 1, "method": "ping"},
                        {"jsonrpc": "2.0", "id": True, "method": "ping"}]:
            self.assertEqual(server.handle_rpc(invalid)["error"]["code"], -32600)

    def test_agent_exception_does_not_terminate_stream(self):
        agent = FakeAgent()
        agent.poll_reminders = Mock(side_effect=RuntimeError("private failure"))
        output = io.StringIO()
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "poll_reminders", "arguments": {"request_id": "r"}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "ping"}]
        serve_stdio(AgendaMCP(agent), input_stream=io.StringIO("\n".join(map(json.dumps, messages))), output_stream=output)
        replies = list(map(json.loads, output.getvalue().splitlines()))
        self.assertTrue(replies[0]["result"]["isError"])
        self.assertEqual(replies[1]["result"], {})
        self.assertNotIn("private failure", output.getvalue())

    def test_agent_business_error_is_preserved(self):
        agent = FakeAgent()
        body = {"success": False, "retryable": False, "error": {"code": "SQL_NOT_ALLOWED", "message": "rejected"}}
        agent.poll_reminders = Mock(return_value=body)
        self.assertEqual(AgendaMCP(agent).call_tool("poll_reminders", {"request_id": "r"}), body)

    def test_stdio_agent_backend_auth_error_is_transparent(self):
        backend_calls = []

        def backend_call(payload):
            backend_calls.append(payload)
            return {"success": False, "retryable": False,
                    "error": {"code": "PERMISSION_DENIED", "message": "服务令牌无效"}}

        server = build_server(backend_call)
        request = {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                   "params": {"name": "poll_reminders", "arguments": {"request_id": "r"}}}
        incoming = io.StringIO(json.dumps(request) + "\n")
        output = io.StringIO()
        serve_stdio(server, input_stream=incoming, output_stream=output)

        response = json.loads(output.getvalue())
        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["error"]["code"],
                         "PERMISSION_DENIED")
        self.assertEqual(len(backend_calls), 1)
        self.assertEqual(backend_calls[0]["operation"], "POLL_REMINDERS")

    def test_stdio_subprocess_reaches_backend_through_agent(self):
        http_server = make_server("127.0.0.1", 0, app)
        worker = threading.Thread(target=http_server.serve_forever, daemon=True)
        worker.start()
        environment = os.environ.copy()
        environment["SCHEDULE_BACKEND_URL"] = f"http://127.0.0.1:{http_server.server_port}"
        environment.pop("SCHEDULE_INTERNAL_SERVICE_TOKEN", None)
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "poll_reminders", "arguments": {"request_id": "stdio-test"}}},
        ]
        try:
            with patch("app.INTERNAL_SERVICE_TOKEN", "stdio-test-token"):
                completed = subprocess.run(
                    [sys.executable, "mcp.py"], input="\n".join(map(json.dumps, messages)) + "\n",
                    text=True, capture_output=True, timeout=10, env=environment,
                )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            responses = [json.loads(line) for line in completed.stdout.splitlines()]
            result = responses[1]["result"]
            self.assertTrue(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"])["error"]["code"],
                             "PERMISSION_DENIED")
        finally:
            http_server.shutdown()
            worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
