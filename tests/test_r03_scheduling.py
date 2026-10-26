"""R03：配置边界、跨日期时区和真实自动排期写入验收。"""
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import db
from agent import AgendaAgent
import test_t06_auto_schedule as t06

NOW = t06.NOW


class SchedulingConfigTests(unittest.TestCase):
    def test_horizon_uses_local_today_and_inclusive_last_day(self):
        # UTC 10 月 9 日仍是洛杉矶 10 月 8 日，范围必须按请求时区判断。
        now = datetime(2040, 10, 9, 1, tzinfo=ZoneInfo('UTC'))
        backend = Mock(return_value={'success': True, 'results': []})
        agent = AgendaAgent(backend, clock=lambda: now)
        with patch('config.SCHEDULE_HORIZON_DAYS', 2):
            result = agent.find_available_slots('r03-range', date='2040-10-08',
                                                end_date='2040-10-09', timezone='America/Los_Angeles')
            self.assertTrue(result['success'], result)
            statements = backend.call_args.args[0]['statements']
            self.assertEqual(statements[0]['params'][2:],
                             ['2040-10-10 07:00:00', '2040-10-08 07:00:00'])
            self.assertEqual(statements[1]['params'], ['2040-10-08', '2040-10-09'])
            for first, last in [('2040-10-07', '2040-10-08'),
                                ('2040-10-09', '2040-10-10'),
                                ('2040-10-09', '2040-10-08')]:
                backend.reset_mock()
                rejected = agent.find_available_slots('r03-range', date=first,
                                                     end_date=last, timezone='America/Los_Angeles')
                self.assertEqual(rejected['error']['code'], 'INVALID_ARGUMENT')
                backend.assert_not_called()

    def test_custom_windows_merge_both_occupancies_and_round_up(self):
        backend = Mock(return_value={'success': True, 'results': [
            {'rows': [{'start_at': '2040-10-10 01:05:00', 'end_at': '2040-10-10 01:20:00'}]},
            {'rows': [{'event_date': '2040-10-10', 'start_time': '09:15:00', 'end_time': '09:32:00'}]},
        ]})
        agent = AgendaAgent(backend, clock=lambda: NOW)
        with patch('config.WORK_HOURS', [(9, 2, 10, 5), (14, 0, 14, 20)]):
            result = agent.find_available_slots('r03-windows', date='2040-10-10')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['slots'], [{'start_at': '2040-10-10 09:35:00',
                                          'end_at': '2040-10-10 10:05:00', 'timezone': 'Asia/Shanghai'}])

    def test_offset_deadline_limits_complete_duration(self):
        backend = Mock(return_value={'success': True, 'results': []})
        agent = AgendaAgent(backend, clock=lambda: NOW)
        with patch('config.WORK_HOURS', [(9, 0, 10, 0)]):
            result = agent.find_available_slots('r03-deadline', date='2040-10-10',
                                                deadline='2040-10-10T01:30:00Z')
            self.assertEqual(len(result['slots']), 1)
            self.assertEqual(result['slots'][0]['end_at'], '2040-10-10 09:30:00')
            result = agent.find_available_slots('r03-deadline', date='2040-10-10',
                                                deadline='2040-10-10T01:29:59Z')
            self.assertEqual(result['error']['code'], 'NO_AVAILABLE_SLOT')


class SchedulingMySQLTests(t06.AutoScheduleMySQLTests):
    # 复用 T06 的真实数据库夹具和清理，并保留并发冲突/回滚回归。
    def test_configured_window_query_boundary_and_written_utc(self):
        request_id = self.request_id('-r03-window')
        calls = []
        def backend(payload):
            response = self.post(payload)
            calls.append((payload, response))
            return response
        with patch('config.WORK_HOURS', [(10, 2, 11, 0)]), patch('config.SCHEDULE_HORIZON_DAYS', 2):
            result = AgendaAgent(backend, clock=lambda: NOW).create_schedule('明天写周报', request_id)
            self.assertTrue(result['success'], result)
            query, occupancy = calls[0]
            self.assertNotIn('slots', occupancy)
            self.assertEqual(query['statements'][0]['params'][2:],
                             ['2040-10-10 16:00:00', '2040-10-09 16:00:00'])
            with db.get_conn() as conn, conn.cursor() as c:
                for statement, index in zip(query['statements'],
                                            ['idx_scheduled_tasks_status_time', 'idx_calendar_events_date_time']):
                    c.execute('EXPLAIN ' + statement['sql'], tuple(statement['params']))
                    self.assertIn(index, c.fetchone()['possible_keys'])
            row = self.rows(request_id)[0]
            self.assertEqual(row['start_at'], datetime(2040, 10, 10, 2, 5))
            self.assertEqual(row['end_at'], datetime(2040, 10, 10, 2, 35))
            self.assertEqual(row['timezone'], 'Asia/Shanghai')
            self.assertEqual(row['schedule_source'], 'AUTO')
            self.assertEqual(result['schedule']['start_at'], '2040-10-10 02:05:00')
            # 后端独立拒绝范围越界，不能仅依赖 Agent 校验。
            rejected = dict(query, date='2040-10-11', end_date='2040-10-11')
            self.assertEqual(self.post(rejected)['error']['code'], 'INVALID_ARGUMENT')


if __name__ == '__main__':
    unittest.main()
