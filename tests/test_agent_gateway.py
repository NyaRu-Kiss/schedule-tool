import unittest
from unittest.mock import Mock, patch

import requests

from agent_gateway import backend_call_from_env


class AgentGatewayTests(unittest.TestCase):
    @patch("agent_gateway.requests.post")
    def test_backend_url_auth_and_business_error(self, post):
        body = {"success": False, "retryable": False,
                "error": {"code": "PERMISSION_DENIED", "message": "denied"}}
        post.return_value.json.return_value = body
        with patch.dict("os.environ", {
            "SCHEDULE_BACKEND_URL": "http://backend.test/",
            "SCHEDULE_INTERNAL_SERVICE_TOKEN": "agent-test-token",
        }, clear=True):
            result = backend_call_from_env()({"operation": "POLL_REMINDERS"})

        self.assertEqual(result, body)
        self.assertEqual(post.call_args.args[0],
                         "http://backend.test/api/internal/sql/execute")
        self.assertEqual(post.call_args.kwargs["headers"],
                         {"Authorization": "Bearer agent-test-token"})

    @patch("agent_gateway.requests.post")
    def test_transport_and_invalid_response_become_nonretryable(self, post):
        post.side_effect = requests.ConnectionError("private endpoint")
        result = backend_call_from_env()({"operation": "POLL_REMINDERS"})
        self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")
        self.assertFalse(result["retryable"])

        post.side_effect = None
        post.return_value.json.return_value = []
        result = backend_call_from_env()({"operation": "POLL_REMINDERS"})
        self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")
        self.assertFalse(result["retryable"])


if __name__ == "__main__":
    unittest.main()
