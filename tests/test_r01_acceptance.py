"""R01 验收：认证边界与内部操作防绕过；失败用例保留为整改依据。"""
import threading
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import requests
from werkzeug.serving import make_server

import app as backend
import sql_executor


class R01AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = backend.app.test_client()
        self.token = patch.object(backend, 'INTERNAL_SERVICE_TOKEN', 'r01-test-token')
        self.token.start()
        self.addCleanup(self.token.stop)
        self.headers = {'Authorization': 'Bearer r01-test-token'}
        self.request_id = 'R01-' + uuid4().hex
        self.addCleanup(sql_executor._cache.pop, self.request_id, None)

    def payload(self, operation='SQL_BATCH'):
        return {'request_id': self.request_id, 'operation': operation,
                'statements': [{'sql': 'UPDATE scheduled_tasks SET reminder_status=%s WHERE id=%s',
                                'params': ['SENT', 123]}]}

    def assert_rejected_before_database(self, payload):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = None
        cursor.rowcount = 1
        cursor.lastrowid = 0
        connection.cursor.return_value = cursor
        with patch.object(sql_executor.db, 'get_conn', return_value=connection) as get_conn:
            response = self.client.post('/api/internal/sql/execute', json=payload,
                                        headers=self.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(response.get_json()['error']['code'], 'SQL_NOT_ALLOWED')
        get_conn.assert_not_called()

    def test_missing_and_forged_service_credentials_are_rejected(self):
        for headers in ({}, {'Authorization': 'Bearer wrong', 'X-Source': 'agent',
                            'X-User-Id': 'admin'}):
            with self.subTest(headers=headers), patch.object(sql_executor.db, 'get_conn') as get_conn, \
                    self.assertLogs('audit', level='WARNING') as logs:
                response = self.client.post('/api/internal/sql/execute',
                                            json=self.payload(), headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(response.get_json()['retryable'])
                get_conn.assert_not_called()
                self.assertTrue(any('authentication_failed' in line and 'PERMISSION_DENIED' in line
                                    for line in logs.output))

    def test_unauthorized_column_is_rejected(self):
        payload = self.payload()
        payload['statements'][0]['sql'] = 'UPDATE scheduled_tasks SET tenant_id=%s WHERE id=%s'
        self.assert_rejected_before_database(payload)

    def test_sql_batch_cannot_bypass_reminder_confirmation(self):
        with self.assertLogs('audit', level='WARNING') as logs:
            self.assert_rejected_before_database(self.payload())
        self.assertTrue(any('request_rejected' in line and 'SQL_NOT_ALLOWED' in line for line in logs.output))

    def test_unknown_operation_is_rejected(self):
        self.assert_rejected_before_database(self.payload('UNAUTHORIZED_OPERATION'))

    def test_missing_operation_cannot_default_to_arbitrary_sql(self):
        payload = self.payload()
        del payload['operation']
        self.assert_rejected_before_database(payload)

    def test_poll_reminders_cannot_write(self):
        self.assert_rejected_before_database(self.payload('POLL_REMINDERS'))

    def test_sql_batch_cannot_bypass_schedule_validation(self):
        payload = self.payload()
        payload['statements'] = [{'sql': 'UPDATE scheduled_tasks SET end_at=%s WHERE id=%s',
                                  'params': ['2000-01-01 00:00:00', 123]}]
        self.assert_rejected_before_database(payload)

    def test_real_http_frontend_is_public_and_internal_sql_is_authenticated(self):
        with patch.object(backend, '_db_ready', True), \
                patch.object(backend.db, 'list_todos', return_value=[]):
            server = make_server('127.0.0.1', 0, backend.app)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                url = f'http://127.0.0.1:{server.server_port}'
                frontend = requests.get(url + '/api/todos', timeout=5)
                self.assertEqual(frontend.status_code, 200)
                self.assertEqual(frontend.json(), [])
                internal = requests.post(url + '/api/internal/sql/execute', json={}, timeout=5)
                self.assertEqual(internal.status_code, 403)
            finally:
                server.shutdown()
                worker.join(timeout=5)
                server.server_close()
            self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
