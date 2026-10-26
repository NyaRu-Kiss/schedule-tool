"""T05：Agent 空档计算、后端范围防绕过和真实 MySQL 查询。"""
import copy
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo
import config
import db
import sql_executor
from agent import AgendaAgent
from app import app

NOW = datetime(2026, 10, 9, 8, tzinfo=ZoneInfo('Asia/Shanghai'))


class AvailabilityTests(unittest.TestCase):
    def find(self, rows=(), **kwargs):
        backend = Mock(return_value={'success': True, 'results': [{'rows': list(rows)}]})
        agent = AgendaAgent(backend, clock=lambda: NOW)
        return agent.find_available_slots('t05', date='2026-10-10', **kwargs), backend

    def test_both_occupancies_and_default_duration(self):
        rows = [dict(start_at='2026-10-10 01:00:00', end_at='2026-10-10 02:00:00'),
                dict(event_date='2026-10-10', start_time='10:00:00', end_time='11:00:00')]
        result, backend = self.find(rows)
        self.assertEqual(result['slots'][0]['start_at'], '2026-10-10 11:00:00')
        self.assertEqual(result['slots'][0]['end_at'], '2026-10-10 11:30:00')
        statements = backend.call_args.args[0]['statements']
        self.assertEqual(statements[0]['params'][2:], ['2026-10-10 16:00:00', '2026-10-09 16:00:00'])
        self.assertEqual(len(statements), 2)
        self.assertTrue(all(s['sql'].startswith('SELECT') for s in statements))

    def test_work_windows_deadline_and_no_slots(self):
        with patch('config.WORK_HOURS', [(9, 0, 9, 20), (14, 0, 15, 0)]):
            result, _ = self.find(deadline='2026-10-10T14:30:00+08:00')
            self.assertEqual(len(result['slots']), 1)
            self.assertEqual(result['slots'][0]['start_at'], '2026-10-10 14:00:00')
            result, _ = self.find(deadline='2026-10-10T14:29:00+08:00')
            self.assertEqual(result['error']['code'], 'NO_AVAILABLE_SLOT')
        result, _ = self.find([dict(event_date='2026-10-10', start_time='00:00:00', end_time='23:59:59')])
        self.assertEqual(result['error']['code'], 'NO_AVAILABLE_SLOT')

    def test_rounds_up_current_time_and_respects_range(self):
        agent = AgendaAgent(Mock(return_value={'success': True, 'results': []}),
                            clock=lambda: NOW.replace(hour=9, minute=1, second=1))
        result = agent.find_available_slots('r', date='2026-10-09')
        self.assertEqual(result['slots'][0]['start_at'], '2026-10-09 09:05:00')
        result = agent.find_available_slots('r', date='2026-10-10', end_date='2026-10-11')
        self.assertEqual({s['start_at'][:10] for s in result['slots']}, {'2026-10-10', '2026-10-11'})
        for day in ['2026-10-08', '2026-10-16', 'bad']:
            agent.backend_call.reset_mock()
            self.assertFalse(agent.find_available_slots('r', date=day)['success'])
            agent.backend_call.assert_not_called()

    def test_utc_and_inactive_filter_and_fresh_query(self):
        result, backend = self.find([dict(start_at='2026-10-10 09:00:00', end_at='2026-10-10 10:00:00')], timezone='UTC')
        self.assertEqual(result['slots'][0]['start_at'], '2026-10-10 10:00:00')
        payload = backend.call_args.args[0]
        with patch('sql_executor.datetime') as clock, patch('sql_executor.db.get_conn') as connect:
            clock.now.return_value = NOW
            bad = copy.deepcopy(payload)
            bad['statements'][0]['params'][2] = '2099-01-01 00:00:00'
            self.assertEqual(sql_executor.execute(bad)['error']['code'], 'SQL_NOT_ALLOWED')
            bad = copy.deepcopy(payload)
            bad['statements'][0]['sql'] += ' OR status=%s'
            bad['statements'][0]['params'].append('CANCELLED')
            self.assertEqual(sql_executor.execute(bad)['error']['code'], 'SQL_NOT_ALLOWED')
            bad = copy.deepcopy(payload)
            bad['date'] = '2026-10-16'
            self.assertEqual(sql_executor.execute(bad)['error']['code'], 'INVALID_ARGUMENT')
            connect.assert_not_called()


@unittest.skipUnless(config.DB_BACKEND == 'mysql', '需要已迁移的真实 MySQL')
class MySQLAvailabilityTests(unittest.TestCase):
    def test_timezones_indexes_auth_and_repeated_reads(self):
        prefix = 'T05-' + uuid4().hex
        day = '2040-10-10'
        now = datetime(2040, 10, 9, 8, tzinfo=ZoneInfo('Asia/Shanghai'))
        client = app.test_client()
        payloads = []
        def call(payload):
            payloads.append(payload)
            return client.post('/api/internal/sql/execute', json=payload,
                               headers={'Authorization': 'Bearer t05-token'}).get_json()
        try:
            with db.get_conn() as conn, conn.cursor() as c:
                c.execute('INSERT INTO todos (title,created_at,updated_at,request_id) VALUES (%s,%s,%s,%s)',
                          ('T05 fixture', day, day, prefix))
                todo = c.lastrowid
                c.execute('INSERT INTO scheduled_tasks (todo_id,start_at,end_at,created_at) VALUES (%s,%s,%s,%s)',
                          (todo, day + ' 01:00:00', day + ' 02:00:00', day))
                c.execute('SELECT id FROM event_types LIMIT 1')
                type_id = c.fetchone()['id']
                c.execute('INSERT INTO calendar_events (id,type_id,title,event_date,start_time,end_time) VALUES (%s,%s,%s,%s,%s,%s)',
                          (prefix, type_id, 'T05 fixture', day, '10:00:00', '11:00:00'))
            class FrozenDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return now.astimezone(tz)
            with patch('app.INTERNAL_SERVICE_TOKEN', 't05-token'), patch('sql_executor.datetime', FrozenDatetime):
                agent = AgendaAgent(call, clock=lambda: now)
                result = agent.find_available_slots(prefix, date=day)
                self.assertTrue(result['success'], result)
                self.assertEqual(result['slots'][0]['start_at'], day + ' 11:00:00')
                self.assertEqual(client.post('/api/internal/sql/execute', json=payloads[-1]).status_code, 403)
                self.assertNotIn('slots', call(payloads[-1]))
                with db.get_conn() as conn, conn.cursor() as c:
                    for statement, expected in zip(payloads[-1]['statements'], ['idx_scheduled_tasks_status_time', 'idx_calendar_events_date_time']):
                        c.execute('EXPLAIN ' + statement['sql'], tuple(statement['params']))
                        plan = c.fetchone()
                        self.assertIn(expected, plan['possible_keys'])
                    c.execute('UPDATE scheduled_tasks SET status=%s WHERE todo_id=%s', ('CANCELLED', todo))
                fresh = agent.find_available_slots(prefix, date=day)
                self.assertEqual(fresh['slots'][0]['start_at'], day + ' 09:00:00')
                with db.get_conn() as conn, conn.cursor() as c:
                    c.execute('UPDATE scheduled_tasks SET status=%s,start_at=%s,end_at=%s WHERE todo_id=%s',
                              ('ACTIVE', day + ' 09:00:00', day + ' 10:00:00', todo))
                utc = agent.find_available_slots(prefix, date=day, timezone='UTC')
                self.assertEqual(utc['slots'][0]['start_at'], day + ' 11:00:00')
                self.assertTrue(all(s['start_at'][11:16] != '10:00' for s in utc['slots']))
                with db.get_conn() as conn, conn.cursor() as c:
                    c.execute('SELECT COUNT(*) AS n FROM todos WHERE request_id=%s', (prefix,))
                    self.assertEqual(c.fetchone()['n'], 1)
        finally:
            with db.get_conn() as conn, conn.cursor() as c:
                c.execute('DELETE FROM calendar_events WHERE id=%s', (prefix,))
                c.execute('DELETE s FROM scheduled_tasks s JOIN todos t ON s.todo_id=t.id WHERE t.request_id=%s', (prefix,))
                c.execute('DELETE FROM todos WHERE request_id=%s', (prefix,))
