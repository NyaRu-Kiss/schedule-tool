import json
import threading
import unittest
from unittest.mock import patch

import requests
from werkzeug.serving import make_server

from app import app as backend_app
from mcp import AgendaMCP
from mcp_http import create_http_app
from test_mcp import FakeAgent


HEADERS = {"Authorization": "Bearer http-test-token",
           "Accept": "application/json, text/event-stream"}


class HTTPMCPTests(unittest.TestCase):
    def setUp(self):
        self.agent = FakeAgent()
        self.app = create_http_app(lambda: AgendaMCP(self.agent), token="http-test-token",
                                   allowed_origins=["https://client.example"])
        self.client = self.app.test_client()

    def post(self, message, **headers):
        return self.client.post("/mcp", json=message, headers={**HEADERS, **headers})

    def test_initialize_list_and_all_tools(self):
        init = self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(init.json["result"]["protocolVersion"], "2025-06-18")
        self.assertNotIn("Mcp-Session-Id", init.headers)
        notify = self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((notify.status_code, notify.data), (202, b""))
        listing = self.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual([t["name"] for t in listing.json["result"]["tools"]], list(AgendaMCP.TOOL_NAMES))
        for name, args, kind in [
            ("create_schedule", {"text": "开会", "request_id": "create"}, "create"),
            ("poll_reminders", {"request_id": "poll"}, "poll"),
            ("ack_reminder", {"request_id": "ack", "scheduled_task_id": 1, "idempotency_key": "k"}, "ack"),
        ]:
            response = self.post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": name, "arguments": args}},
                                 **{"MCP-Protocol-Version": "2025-06-18"})
            self.assertEqual(response.status_code, 200)
            result = response.json["result"]
            self.assertEqual(result["structuredContent"], {"success": True, "kind": kind})
            self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])

    def test_auth_origin_and_http_contract(self):
        message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        self.assertEqual(self.post(message, Authorization="").status_code, 401)
        self.assertEqual(self.post(message, Authorization="Bearer backend-token").status_code, 401)
        self.assertEqual(self.post(message, Origin="https://evil.example").status_code, 403)
        self.assertEqual(self.post(message, Origin="https://client.example").status_code, 200)
        self.assertEqual(self.post(message, Accept="application/json").status_code, 406)
        self.assertEqual(self.post(message, **{"MCP-Protocol-Version": "invalid"}).status_code, 400)
        self.assertEqual(self.client.post("/mcp", data="{}", headers=HEADERS).status_code, 415)
        for method in [self.client.get, self.client.delete]:
            response = method("/mcp", headers=HEADERS)
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.headers["Allow"], "POST")
        self.assertEqual(self.agent.calls, [])
        with self.assertRaises(ValueError):
            create_http_app(token="")

    def test_bad_messages_and_client_responses(self):
        for body, code in [("{", -32700), ('{"value":NaN}', -32700), ("[]", -32600),
                           ('{"jsonrpc":"2.0","id":true,"method":"ping"}', -32600)]:
            result = self.client.post("/mcp", data=body, content_type="application/json", headers=HEADERS)
            self.assertEqual(result.status_code, 400)
            self.assertEqual(result.json["error"]["code"], code)
        response = self.post({"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual((response.status_code, response.data), (202, b""))
        unknown = self.post({"jsonrpc": "2.0", "id": "unknown", "method": "unknown"})
        self.assertEqual(unknown.json["error"]["code"], -32601)
        oversized = self.client.post("/mcp", data=b" " * (1024 * 1024 + 1),
                                     content_type="application/json", headers=HEADERS)
        self.assertEqual(oversized.status_code, 413)

    def test_protocol_version_is_not_shared_between_clients(self):
        self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-11-25"}})
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "poll_reminders", "arguments": {"request_id": "r"}}}
        self.assertIn("structuredContent", self.post(call, **{"MCP-Protocol-Version": "2025-06-18"}).json["result"])
        self.assertNotIn("structuredContent", self.post(call).json["result"])

    def test_real_http_reaches_backend_via_agent_and_closes_services(self):
        backend = make_server("127.0.0.1", 0, backend_app)
        servers = [backend]
        workers = []
        try:
            with patch.dict("os.environ", {"SCHEDULE_BACKEND_URL": f"http://127.0.0.1:{backend.server_port}",
                                           "SCHEDULE_INTERNAL_SERVICE_TOKEN": "wrong"}), \
                    patch("app.INTERNAL_SERVICE_TOKEN", "backend-test-token"):
                gateway = make_server("127.0.0.1", 0, create_http_app(token="http-test-token"))
                servers.append(gateway)
                for server in servers:
                    worker = threading.Thread(target=server.serve_forever, daemon=True)
                    worker.start()
                    workers.append(worker)
                url = f"http://127.0.0.1:{gateway.server_port}/mcp"
                with requests.Session() as session:
                    init = session.post(url, headers=HEADERS, json={"jsonrpc": "2.0", "id": 1,
                        "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, timeout=5)
                    self.assertEqual(init.status_code, 200)
                    result = session.post(url, headers={**HEADERS, "MCP-Protocol-Version": "2025-06-18"},
                        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "poll_reminders", "arguments": {"request_id": "http-test"}}},
                        timeout=5).json()["result"]
                    self.assertTrue(result["isError"])
                    self.assertEqual(result["structuredContent"]["error"]["code"], "PERMISSION_DENIED")
                    self.assertFalse(result["structuredContent"]["retryable"])
        finally:
            for server, worker in zip(servers, workers):
                server.shutdown()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
            for server in servers:
                server.server_close()


if __name__ == "__main__":
    unittest.main()
