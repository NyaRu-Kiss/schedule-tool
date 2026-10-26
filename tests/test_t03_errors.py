"""T03：业务错误协议、重试决策及真实本地 HTTP 边界。

HTTP 使用真实 Flask 路由；数据库故障注入，不启动 MySQL。
"""
import threading
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests
from werkzeug.serving import make_server

from agent import AgendaAgent
from app import app
from mcp import AgendaMCP
import sql_executor


class T03ErrorTests(unittest.TestCase):
    def assert_error(self, body, code, retryable=False):
        self.assertIs(body['success'], False)
        self.assertIs(body['retryable'], retryable)
        self.assertEqual(set(body['error']), {'code', 'message'})
        self.assertEqual(body['error']['code'], code)
        self.assertIsInstance(body['error']['message'], str)

    def agent(self, backend):
        return AgendaAgent(backend, clock=lambda: datetime(2026, 10, 9, 9, tzinfo=ZoneInfo('Asia/Shanghai')))

    def test_all_backend_codes_and_nonretryable_stop(self):
        expected = {'INVALID_ARGUMENT', 'TIME_CONFLICT', 'POLICY_LIMIT',
                    'NO_AVAILABLE_SLOT', 'NOT_FOUND', 'PERMISSION_DENIED',
                    'SQL_NOT_ALLOWED', 'IDEMPOTENCY_CONFLICT', 'INTERNAL_ERROR'}
        self.assertEqual(sql_executor.ERROR_CODES, expected)
        for code in sorted(expected):
            with self.subTest(code=code):
                retryable = code in {'TIME_CONFLICT', 'NO_AVAILABLE_SLOT'}
                body = sql_executor.make_error_response('r', 1, code, '测试错误')
                self.assert_error(body, code, retryable)
                backend = Mock(return_value=body)
                result = self.agent(backend).poll_reminders('r')
                self.assertEqual(result, body)
                self.assertEqual(backend.call_count, 3 if retryable else 1)

    def test_agent_local_parameter_errors_never_call_backend(self):
        backend = Mock()
        agent = self.agent(backend)
        calls = [lambda: agent.create_schedule('', 'r'),
                 lambda: agent.create_schedule('明天开会', None),
                 lambda: agent.create_schedule('明天25点开会', 'r'),
                 lambda: agent.create_schedule('2026-02-30开会', 'r'),
                 lambda: agent.create_schedule('明天开会', 'r', timezone='invalid/zone'),
                 lambda: agent.poll_reminders(''),
                 lambda: agent.poll_reminders('r', limit=True),
                 lambda: agent.poll_reminders('r', now='bad'),
                 lambda: agent.ack_reminder('r', 0, 'k')]
        for call in calls:
            self.assert_error(call(), 'INVALID_ARGUMENT')
        backend.assert_not_called()

    def test_agent_no_slots_error(self):
        backend = Mock(return_value={'success': True, 'results': [{'rows': [{'event_date': '2026-10-10', 'start_time': '00:00:00', 'end_time': '23:59:59'}]}]})
        self.assert_error(self.agent(backend).create_schedule('明天写周报', 'r'),
                          'NO_AVAILABLE_SLOT', True)
        backend.assert_called_once()

    def test_mcp_local_errors_and_exception(self):
        agent = Mock()
        server = AgendaMCP(agent)
        self.assert_error(server.call_tool('unknown', {}), 'INVALID_ARGUMENT')
        self.assert_error(server.call_tool('poll_reminders', {}), 'INVALID_ARGUMENT')
        self.assert_error(server.call_tool('create_schedule',
                          {'text': 'x', 'request_id': 'r', 'timezone': 'bad'}), 'INVALID_ARGUMENT')
        agent.poll_reminders.side_effect = RuntimeError('private failure')
        result = server.call_tool('poll_reminders', {'request_id': 'r'})
        self.assert_error(result, 'INTERNAL_ERROR')
        self.assertNotIn('private failure', str(result))

    def test_mcp_preserves_agent_error_without_retry(self):
        agent = Mock()
        body = {'success': False, 'retryable': False,
                'error': {'code': 'PERMISSION_DENIED', 'message': 'denied'}}
        agent.poll_reminders.return_value = body
        self.assertEqual(AgendaMCP(agent).call_tool('poll_reminders', {'request_id': 'r'}), body)
        agent.poll_reminders.assert_called_once()

    def test_real_http_errors_visible_to_agent(self):
        server = make_server('127.0.0.1', 0, app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f'http://127.0.0.1:{server.server_port}/api/internal/sql/execute'
        try:
            with patch('app.INTERNAL_SERVICE_TOKEN', 't03-test-token'):
                for code, payload, token in [
                    ('PERMISSION_DENIED', {}, None),
                    ('INVALID_ARGUMENT', {}, 't03-test-token'),
                    ('SQL_NOT_ALLOWED', {'request_id': 't03-http-sql', 'operation': 'SQL_BATCH',
                     'statements': [{'sql': 'DELETE FROM todos WHERE id=%s', 'params': [1]}]},
                     't03-test-token'),
                    ('INTERNAL_ERROR', {'request_id': 't03-http-internal', 'operation': 'SQL_BATCH',
                     'statements': [{'sql': 'SELECT id FROM todos', 'params': []}]}, 't03-test-token'),
                ]:
                    with self.subTest(code=code), patch('sql_executor.db.get_conn',
                                                       side_effect=RuntimeError('private database')):
                        seen = []
                        def backend(request):
                            headers = {'Authorization': f'Bearer {token}'} if token else {}
                            response = requests.post(url, json=payload, headers=headers, timeout=5)
                            self.assertEqual(response.status_code, sql_executor.HTTP_STATUS_BY_CODE[code])
                            seen.append(response.json())
                            return seen[-1]
                        result = self.agent(backend).poll_reminders('t03-http')
                        self.assert_error(result, code)
                        self.assertEqual(len(seen), 1)
                        self.assertNotIn('private database', str(result))
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()
        self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
