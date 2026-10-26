import unittest
from unittest.mock import patch

from app import app
import sql_executor


class T02ExecutorTests(unittest.TestCase):
    def test_internal_route_requires_service_token(self):
        client = app.test_client()
        with patch("app.INTERNAL_SERVICE_TOKEN", "secret"):
            response = client.post("/api/internal/sql/execute", json={})
        self.assertEqual(response.status_code, 403)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertFalse(body["retryable"])
        self.assertEqual(body["error"]["code"], "PERMISSION_DENIED")

    def test_internal_route_accepts_token_and_reaches_validator(self):
        client = app.test_client()
        payload = {
            "request_id": "t02-auth",
            "attempt": 1,
            "max_attempts": 3,
            "operation": "SQL_BATCH",
            "statements": [{"sql": "DELETE FROM todos WHERE id=%s", "params": [1]}],
        }
        with patch("app.INTERNAL_SERVICE_TOKEN", "secret"):
            response = client.post(
                "/api/internal/sql/execute", json=payload,
                headers={"Authorization": "Bearer secret"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "SQL_NOT_ALLOWED")

    def test_invalid_table_field_and_unbound_sql_are_rejected(self):
        base = {"request_id": "t02-validation", "attempt": 1, "max_attempts": 3, "operation": "SQL_BATCH"}
        cases = [
            {"sql": "SELECT password FROM users", "params": []},
            {"sql": "SELECT title FROM todos", "params": ["unused"]},
            {"sql": "SELECT title FROM todos; SELECT id FROM todos", "params": []},
        ]
        for statement in cases:
            with self.subTest(statement=statement):
                response = sql_executor.execute(dict(base, statements=[statement]))
                self.assertFalse(response["success"])
                self.assertIn(response["error"]["code"], {"SQL_NOT_ALLOWED", "INVALID_ARGUMENT"})

    def test_attempt_limit_rejects_fourth_attempt(self):
        response = sql_executor.execute({
            "request_id": "t02-attempt", "attempt": 4, "max_attempts": 4,
            "operation": "SQL_BATCH", "statements":[{"sql":"SELECT id FROM todos", "params":[]}],
        })
        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
