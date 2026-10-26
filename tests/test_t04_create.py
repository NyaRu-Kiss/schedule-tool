"""T04：模拟事务测试及已迁移 MySQL 中可清理的隔离记录测试。"""
import copy
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import db
import sql_executor
from agent import AgendaAgent
from app import app
from config import DB_BACKEND


def create_payload(request_id):
    todo = dict(title='T04 指定时间会议', priority=2, estimate_min=30,
                timezone='Asia/Shanghai', request_id=request_id, auto_scheduled=0,
                created_at='2040-10-09T09:00:00+08:00', updated_at='2040-10-09T09:00:00+08:00')
    schedule = dict(todo_id=0, start_at='2040-10-10T15:00:00+08:00',
                    end_at='2040-10-10T15:30:00+08:00', timezone='Asia/Shanghai',
                    schedule_source='MANUAL', reminder_at='2040-10-10T14:55:00+08:00',
                    created_at='2040-10-09T09:00:00+08:00')
    statements = []
    for table, values in [('todos', todo), ('scheduled_tasks', schedule)]:
        statements.append({'sql': f"INSERT INTO {table} ({','.join(values)}) VALUES "
                           f"({','.join(['%s'] * len(values))})", 'params': list(values.values())})
    return dict(request_id=request_id, operation='CREATE_SCHEDULE', attempt=1,
                max_attempts=3, statements=statements)


def set_value(payload, index, field, value):
    statement = payload['statements'][index]
    table, values = sql_executor._insert_bindings(statement['sql'], statement['params'])
    values[field] = value
    statement.update(sql=f"INSERT INTO {table} ({','.join(values)}) VALUES "
                     f"({','.join(['%s'] * len(values))})", params=list(values.values()))


class CreateUnitTests(unittest.TestCase):
    def setUp(self):
        self.request_id = 'T04-unit-' + uuid4().hex
        self.payload = create_payload(self.request_id)

    def tearDown(self):
        sql_executor._cache.pop(self.request_id, None)

    def transaction(self, *, conflict=False, fail_second=False):
        cursor = Mock(description=None, rowcount=1, lastrowid=None)
        cursor.fetchone.return_value = {'id': 9} if conflict else None
        cursor.fetchall.return_value = []
        writes, state = [], []
        def execute(sql, params):
            if sql.startswith('INSERT'):
                writes.append((sql, params))
                if fail_second and len(writes) == 2:
                    raise RuntimeError('injected second write failure')
                cursor.lastrowid = 100 + len(writes)
        cursor.execute.side_effect = execute
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        @contextmanager
        def get_conn():
            try:
                yield conn
                state.append('commit')
            except Exception:
                state.append('rollback')
                raise
        return get_conn, writes, state

    def test_success_normalizes_actual_sql_and_replays(self):
        get_conn, writes, state = self.transaction()
        before = copy.deepcopy(self.payload)
        with patch('sql_executor.db.get_conn', get_conn):
            result = sql_executor.execute(self.payload)
            replay = sql_executor.execute(self.payload)
        self.assertTrue(result['success'], result)
        self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(result['schedule'], replay['schedule'])
        self.assertEqual(state, ['commit'])
        self.assertEqual(len(writes), 2)
        todo = sql_executor._insert_bindings(*writes[0])[1]
        schedule = sql_executor._insert_bindings(*writes[1])[1]
        self.assertEqual(todo['scheduled'], 1)
        self.assertEqual(todo['auto_scheduled'], 0)
        self.assertEqual(schedule['todo_id'], 101)
        self.assertEqual(schedule['start_at'], datetime(2040, 10, 10, 7))
        self.assertEqual(schedule['reminder_at'], datetime(2040, 10, 10, 6, 55))
        self.assertEqual(schedule['status'], 'ACTIVE')
        self.assertEqual(schedule['schedule_source'], 'MANUAL')
        self.assertEqual(result['schedule']['start_at'], '2040-10-10 07:00:00')
        self.assertEqual(self.payload, before)

    def test_conflict_rolls_back_without_inserts(self):
        get_conn, writes, state = self.transaction(conflict=True)
        with patch('sql_executor.db.get_conn', get_conn):
            result = sql_executor.execute(self.payload)
        self.assertEqual(result['error']['code'], 'TIME_CONFLICT')
        self.assertEqual(writes, [])
        # 冲突事务回滚后，用只读事务确认是否为另一进程提交的同请求。
        self.assertEqual(state, ['rollback', 'commit'])

    def test_second_write_failure_rolls_back_and_is_not_cached(self):
        get_conn, writes, state = self.transaction(fail_second=True)
        with patch('sql_executor.db.get_conn', get_conn):
            result = sql_executor.execute(self.payload)
        self.assertEqual(result['error']['code'], 'INTERNAL_ERROR')
        self.assertEqual(len(writes), 2)
        self.assertEqual(state, ['rollback'])
        self.assertNotIn(self.request_id, sql_executor._cache)

    def test_invalid_fields_rejected_before_database(self):
        cases = [(0, 'title', ''), (0, 'title', 123), (0, 'title', 'x' * 501),
                 (0, 'timezone', 'invalid/zone'), (1, 'timezone', 'UTC'),
                 (0, 'estimate_min', True), (0, 'estimate_min', 60),
                 (0, 'auto_scheduled', 1), (0, 'priority', 9),
                 (1, 'end_at', '2040-10-10T14:00:00+08:00'),
                 (1, 'reminder_at', '2040-10-10T16:00:00+08:00'),
                 (1, 'schedule_source', 'AUTO'), (1, 'status', 'CANCELLED'),
                 (1, 'reminder_status', 'SENT'), (0, 'done', 1), (0, 'id', 42)]
        with patch('sql_executor.db.get_conn') as connect:
            for index, field, value in cases:
                with self.subTest(field=field, value=value):
                    payload = copy.deepcopy(self.payload)
                    set_value(payload, index, field, value)
                    self.assertEqual(sql_executor.execute(payload)['error']['code'], 'INVALID_ARGUMENT')
            extra = copy.deepcopy(self.payload)
            extra['statements'].append({'sql': 'UPDATE todos SET done=%s WHERE id=%s', 'params': [1, 9]})
            self.assertEqual(sql_executor.execute(extra)['error']['code'], 'INVALID_ARGUMENT')
            connect.assert_not_called()

    def test_aware_datetime_and_agent_default_duration(self):
        aware = datetime(2040, 10, 10, 15, tzinfo=ZoneInfo('Asia/Shanghai'))
        self.assertEqual(sql_executor._parse_utc_datetime(aware, 'start_at'), datetime(2040, 10, 10, 7))
        captured = []
        def capture(payload):
            captured.append(payload)
            return {'success': True}
        AgendaAgent(capture).create_schedule('2040年10月10日下午三点提醒我开会', self.request_id)
        values = sql_executor._insert_bindings(captured[0]['statements'][0]['sql'],
                                              captured[0]['statements'][0]['params'])[1]
        self.assertEqual(values['estimate_min'], 30)
        self.assertEqual(values['auto_scheduled'], 0)


@unittest.skipUnless(DB_BACKEND == 'mysql', '真实验证需要已迁移的 MySQL')
class CreateMySQLTests(unittest.TestCase):
    def setUp(self):
        self.prefix = 'T04-db-' + uuid4().hex
        self.requests = []
        self.events = []
        self.client = app.test_client()
        self.auth = patch('app.INTERNAL_SERVICE_TOKEN', 't04-test-token')
        self.auth.start()
        self.addCleanup(self.auth.stop)

    def tearDown(self):
        with db.get_conn() as conn:
            with conn.cursor() as cursor:
                for request_id in self.requests:
                    cursor.execute('DELETE s FROM scheduled_tasks s JOIN todos t ON t.id=s.todo_id WHERE t.request_id=%s', (request_id,))
                    cursor.execute('DELETE FROM todos WHERE request_id=%s', (request_id,))
                    sql_executor._cache.pop(request_id, None)
                for event in self.events:
                    cursor.execute('DELETE FROM calendar_events WHERE id=%s', (event,))

    def payload(self, suffix):
        request_id = self.prefix + suffix
        self.requests.append(request_id)
        return create_payload(request_id)

    def post(self, payload, *, authenticated=True):
        return self.client.post('/api/internal/sql/execute', json=payload,
                                headers={'Authorization': 'Bearer t04-test-token'} if authenticated else {})

    def rows(self, request_id):
        with db.get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT t.auto_scheduled,t.scheduled,s.* FROM todos t '
                               'JOIN scheduled_tasks s ON s.todo_id=t.id WHERE t.request_id=%s', (request_id,))
                return list(cursor.fetchall())

    def test_authenticated_create_utc_replay_and_adjacent_slot(self):
        payload = self.payload('-create')
        self.assertEqual(self.post(payload, authenticated=False).status_code, 403)
        self.assertEqual(self.rows(payload['request_id']), [])
        response = self.post(payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        row = self.rows(payload['request_id'])[0]
        self.assertEqual(row['start_at'], datetime(2040, 10, 10, 7))
        self.assertEqual(row['end_at'], datetime(2040, 10, 10, 7, 30))
        self.assertEqual(row['reminder_at'], datetime(2040, 10, 10, 6, 55))
        self.assertEqual(row['timezone'], 'Asia/Shanghai')
        self.assertEqual((row['schedule_source'], row['auto_scheduled'], row['scheduled']), ('MANUAL', 0, 1))
        self.assertEqual(row['id'], body['schedule']['scheduled_task_id'])
        self.assertEqual(row['todo_id'], body['schedule']['todo_id'])
        replay = self.post(payload).get_json()
        self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(body['schedule'], replay['schedule'])
        self.assertEqual(len(self.rows(payload['request_id'])), 1)
        adjacent = self.payload('-adjacent')
        set_value(adjacent, 1, 'start_at', '2040-10-10T15:30:00+08:00')
        set_value(adjacent, 1, 'end_at', '2040-10-10T16:00:00+08:00')
        self.assertEqual(self.post(adjacent).status_code, 200)
        overlap = self.payload('-overlap')
        result = self.post(overlap)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.get_json()['error']['code'], 'TIME_CONFLICT')
        self.assertEqual(self.rows(overlap['request_id']), [])

    def test_invalid_end_and_second_insert_database_failure_leave_no_todo(self):
        bad = self.payload('-bad')
        set_value(bad, 1, 'end_at', '2040-10-10T14:00:00+08:00')
        self.assertEqual(self.post(bad).status_code, 400)
        first = self.payload('-first')
        key = self.prefix + '-reminder'
        set_value(first, 1, 'reminder_idempotency_key', key)
        self.assertEqual(self.post(first).status_code, 200)
        failed = self.payload('-failed')
        set_value(failed, 1, 'start_at', '2040-10-10T16:00:00+08:00')
        set_value(failed, 1, 'end_at', '2040-10-10T16:30:00+08:00')
        set_value(failed, 1, 'reminder_idempotency_key', key)
        result = self.post(failed)
        self.assertEqual(result.status_code, 500)
        with db.get_conn() as conn:
            with conn.cursor() as cursor:
                for payload in (bad, failed):
                    cursor.execute('SELECT COUNT(*) AS n FROM todos WHERE request_id=%s', (payload['request_id'],))
                    self.assertEqual(cursor.fetchone()['n'], 0)

    def test_manual_calendar_event_conflict(self):
        event_id = self.prefix + '-event'
        self.events.append(event_id)
        with db.get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute('INSERT INTO calendar_events (id,type_id,title,event_date,start_time,end_time) '
                               'VALUES (%s,%s,%s,%s,%s,%s)',
                               (event_id, 'meeting', 'T04 occupied', '2040-10-10', '15:00:00', '16:00:00'))
        payload = self.payload('-calendar')
        result = self.post(payload)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.get_json()['error']['code'], 'TIME_CONFLICT')
        self.assertEqual(self.rows(payload['request_id']), [])


if __name__ == '__main__':
    unittest.main()
