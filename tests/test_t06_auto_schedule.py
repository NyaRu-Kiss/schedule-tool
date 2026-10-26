import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import config
import db
import sql_executor
from agent import AgendaAgent, error_response
from app import app
from test_t04_create import create_payload, set_value

NOW = datetime(2040, 10, 9, 8, tzinfo=ZoneInfo('Asia/Shanghai'))


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


class AutoScheduleTests(unittest.TestCase):
    def test_conflict_requeries_and_uses_next_slot(self):
        calls = []

        def backend(payload):
            calls.append(payload)
            if payload["operation"] == "FIND_AVAILABLE_SLOTS":
                occupied = [] if len([p for p in calls if p["operation"] == "FIND_AVAILABLE_SLOTS"]) == 1 else [
                    {"start_at": "2026-10-10 01:00:00", "end_at": "2026-10-10 02:00:00"}
                ]
                return {"success": True, "results": [{"rows": occupied}, {"rows": []}]}
            if len([p for p in calls if p["operation"] == "AUTO_CREATE_SCHEDULE"]) == 1:
                return {"success": False, "retryable": True,
                        "error": {"code": "TIME_CONFLICT", "message": "冲突"}}
            return {"success": True, "schedule": {"auto_scheduled": 1}}

        agent = AgendaAgent(
            backend,
            clock=lambda: datetime(2026, 10, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        result = agent.create_schedule("明天安排一小时写周报", "t06-requery")
        self.assertTrue(result["success"])
        self.assertEqual(
            [(p["operation"], p["attempt"]) for p in calls],
            [("FIND_AVAILABLE_SLOTS", 1), ("AUTO_CREATE_SCHEDULE", 1),
             ("FIND_AVAILABLE_SLOTS", 2), ("AUTO_CREATE_SCHEDULE", 2)],
        )
        first_start = calls[1]["statements"][1]["params"][1]
        second_start = calls[3]["statements"][1]["params"][1]
        self.assertNotEqual(first_start, second_start)

    def test_three_rounds_stop_after_requerying(self):
        calls = []

        def backend(payload):
            calls.append(payload)
            if payload["operation"] == "FIND_AVAILABLE_SLOTS":
                return {"success": True, "results": [{"rows": []}, {"rows": []}]}
            return {"success": False, "retryable": True,
                    "error": {"code": "TIME_CONFLICT", "message": "冲突"}}

        agent = AgendaAgent(
            backend,
            clock=lambda: datetime(2026, 10, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        result = agent.create_schedule("明天安排一小时写周报", "t06-limit")
        self.assertFalse(result["success"])
        self.assertEqual(len(calls), 6)
        self.assertEqual([p["attempt"] for p in calls], [1, 1, 2, 2, 3, 3])

    def test_no_slot_never_creates(self):
        backend = Mock(return_value={'success': True, 'results': [{'rows': [
            dict(event_date='2040-10-10', start_time='00:00:00', end_time='23:59:59')
        ]}]})
        result = AgendaAgent(backend, clock=lambda: NOW).create_schedule('明天写周报', 'no-slot')
        self.assertEqual(result['error']['code'], 'NO_AVAILABLE_SLOT')
        backend.assert_called_once()
        self.assertEqual(backend.call_args.args[0]['operation'], 'FIND_AVAILABLE_SLOTS')

    def test_nonretryable_query_or_create_stops(self):
        for fail_query in (True, False):
            with self.subTest(fail_query=fail_query):
                failure = error_response('PERMISSION_DENIED', '拒绝')
                responses = [failure] if fail_query else [
                    {'success': True, 'results': []}, failure]
                backend = Mock(side_effect=responses)
                result = AgendaAgent(backend, clock=lambda: NOW).create_schedule('明天写周报', 'denied')
                self.assertEqual(result, failure)
                self.assertEqual(backend.call_count, 1 if fail_query else 2)

    def test_retryable_query_consumes_one_round(self):
        backend = Mock(side_effect=[error_response('TIME_CONFLICT', '变化', retryable=True),
                                   {'success': True, 'results': []}, {'success': True}])
        result = AgendaAgent(backend, clock=lambda: NOW).create_schedule('明天写周报', 'query-retry')
        self.assertTrue(result['success'])
        self.assertEqual([c.args[0]['attempt'] for c in backend.call_args_list], [1, 2, 2])


@unittest.skipUnless(config.DB_BACKEND == 'mysql', '需要已迁移的真实 MySQL')
class AutoScheduleMySQLTests(unittest.TestCase):
    def setUp(self):
        self.prefix = 'T06-' + uuid4().hex
        self.ids = []
        self.events = []
        for target, value in [('app.INTERNAL_SERVICE_TOKEN', 't06-token'),
                              ('sql_executor.datetime', FrozenDatetime)]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        with db.get_conn() as conn, conn.cursor() as c:
            for request_id in self.ids:
                c.execute('DELETE r FROM sent_reminders r JOIN scheduled_tasks s ON s.id=r.scheduled_task_id '
                          'JOIN todos t ON t.id=s.todo_id WHERE t.request_id=%s', (request_id,))
                c.execute('DELETE s FROM scheduled_tasks s JOIN todos t ON t.id=s.todo_id '
                          'WHERE t.request_id=%s', (request_id,))
                c.execute('DELETE FROM todos WHERE request_id=%s', (request_id,))
                sql_executor._cache.pop(request_id, None)
            for event in self.events:
                c.execute('DELETE FROM calendar_events WHERE id=%s', (event,))

    def request_id(self, suffix):
        value = self.prefix + suffix
        self.ids.append(value)
        return value

    def post(self, payload):
        with app.test_client() as client:
            return client.post('/api/internal/sql/execute', json=payload,
                               headers={'Authorization': 'Bearer t06-token'}).get_json()

    def rows(self, request_id):
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('SELECT t.auto_scheduled,t.scheduled,s.* FROM todos t '
                      'JOIN scheduled_tasks s ON s.todo_id=t.id WHERE t.request_id=%s', (request_id,))
            return list(c.fetchall())

    def test_two_simultaneous_candidates_requery_and_store_nonoverlapping_utc(self):
        barrier = threading.Barrier(2)
        ids = [self.request_id('-a'), self.request_id('-b')]

        def create(request_id):
            calls = []
            def backend(payload):
                response = self.post(payload)
                calls.append((payload, response))
                if payload['operation'] == 'FIND_AVAILABLE_SLOTS' and payload['attempt'] == 1:
                    barrier.wait(timeout=10)
                return response
            result = AgendaAgent(backend, clock=lambda: NOW).create_schedule(
                '明天安排一小时提醒我写周报', request_id)
            return result, calls

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, ids))
        for result, calls in outcomes:
            self.assertTrue(result['success'], result)
            self.assertTrue(result['schedule']['auto_scheduled'])
            self.assertLessEqual(max(p['attempt'] for p, _ in calls), 3)
        lengths = sorted(len(calls) for _, calls in outcomes)
        self.assertEqual(lengths, [2, 4])
        retried = next(calls for _, calls in outcomes if len(calls) == 4)
        self.assertEqual(retried[1][1]['error']['code'], 'TIME_CONFLICT')
        self.assertEqual([(p['operation'], p['attempt']) for p, _ in retried], [
            ('FIND_AVAILABLE_SLOTS', 1), ('AUTO_CREATE_SCHEDULE', 1),
            ('FIND_AVAILABLE_SLOTS', 2), ('AUTO_CREATE_SCHEDULE', 2)])
        rows = sorted([self.rows(r)[0] for r in ids], key=lambda row: row['start_at'])
        self.assertEqual([row['start_at'] for row in rows], [datetime(2040, 10, 10, 1), datetime(2040, 10, 10, 2)])
        self.assertLessEqual(rows[0]['end_at'], rows[1]['start_at'])
        for row, (result, _) in zip([self.rows(r)[0] for r in ids], outcomes):
            self.assertEqual((row['schedule_source'], row['auto_scheduled'], row['scheduled']), ('AUTO', 1, 1))
            self.assertEqual(row['timezone'], 'Asia/Shanghai')
            self.assertEqual(row['start_at'].isoformat(sep=' '), result['schedule']['start_at'])
            self.assertEqual(row['reminder_at'].isoformat(sep=' '), result['schedule']['reminder_at'])

    def test_avoids_manual_calendar_event_and_no_slot(self):
        event_id = self.prefix + '-event'
        self.events.append(event_id)
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('SELECT id FROM event_types LIMIT 1')
            type_id = c.fetchone()['id']
            c.execute('INSERT INTO calendar_events (id,type_id,title,event_date,start_time,end_time) '
                      'VALUES (%s,%s,%s,%s,%s,%s)',
                      (event_id, type_id, 'T06 occupied', '2040-10-10', '09:00:00', '12:00:00'))
        request_id = self.request_id('-event-create')
        result = AgendaAgent(self.post, clock=lambda: NOW).create_schedule('明天写周报', request_id)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['schedule']['start_at'], '2040-10-10 06:00:00')
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('UPDATE calendar_events SET start_time=%s,end_time=%s WHERE id=%s',
                      ('00:00:00', '23:59:59', event_id))
        no_slot_id = self.request_id('-no-slot')
        result = AgendaAgent(self.post, clock=lambda: NOW).create_schedule('明天写周报', no_slot_id)
        self.assertEqual(result['error']['code'], 'NO_AVAILABLE_SLOT')
        self.assertEqual(self.rows(no_slot_id), [])

    def test_auto_second_insert_unique_failure_rolls_back_todo(self):
        existing_id = self.request_id('-existing')
        payload = create_payload(existing_id)
        key = self.prefix + '-unique-key'
        set_value(payload, 1, 'reminder_idempotency_key', key)
        self.assertTrue(self.post(payload)['success'])
        request_id = self.request_id('-rollback')
        def backend(payload):
            if payload['operation'] == 'AUTO_CREATE_SCHEDULE':
                set_value(payload, 1, 'reminder_idempotency_key', key)
            return self.post(payload)
        result = AgendaAgent(backend, clock=lambda: NOW).create_schedule('明天写周报', request_id)
        self.assertEqual(result['error']['code'], 'INTERNAL_ERROR')
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('SELECT COUNT(*) AS n FROM todos WHERE request_id=%s', (request_id,))
            self.assertEqual(c.fetchone()['n'], 0)
        self.assertNotIn(request_id, sql_executor._cache)


if __name__ == "__main__":
    unittest.main()
