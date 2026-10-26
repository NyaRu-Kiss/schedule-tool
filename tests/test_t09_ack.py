"""T09 提醒确认：模拟边界和认证路由到真实 MySQL 的事务验收。"""
import copy
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import config
import db
import sql_executor
from agent import AgendaAgent
from app import app


class AckValidationTests(unittest.TestCase):
    def payload(self):
        backend = Mock(return_value={'success': True})
        AgendaAgent(backend).ack_reminder('t09-validation', 7, 'reminder:7', now='2040-01-01T08:00:00+08:00')
        return backend.call_args.args[0]

    def test_valid_batch_and_utc(self):
        payload = self.payload()
        sql_executor._validate_request(payload)
        self.assertEqual(payload['statements'][0]['params'][4], '2040-01-01 00:00:00')

    def test_status_or_target_or_success_record_cannot_be_forged(self):
        for mutate in (
            lambda p: p['statements'][0]['params'].__setitem__(0, 'FAILED'),
            lambda p: p['statements'][0].__setitem__('sql', p['statements'][0]['sql'].replace('WHERE id=%s', 'WHERE id>=%s')),
            lambda p: p['statements'][1]['params'].__setitem__(0, 8),
        ):
            payload = copy.deepcopy(self.payload())
            mutate(payload)
            with patch('sql_executor.db.get_conn') as connect:
                self.assertFalse(sql_executor.execute(payload)['success'])
                connect.assert_not_called()


@unittest.skipUnless(config.DB_BACKEND == 'mysql', '需要已迁移的真实 MySQL')
class AckMySQLTests(unittest.TestCase):
    def setUp(self):
        self.prefix = 'T09-' + uuid4().hex
        self.tasks = []
        self.todos = []
        self.requests = []
        token = patch('app.INTERNAL_SERVICE_TOKEN', 't09-token')
        token.start()
        self.addCleanup(token.stop)
        self.agent = AgendaAgent(self.post)
        self.addCleanup(self.cleanup_records)

    def post(self, payload):
        self.requests.append(payload['request_id'])
        return app.test_client().post('/api/internal/sql/execute', json=payload,
                                     headers={'Authorization': 'Bearer t09-token'}).get_json()

    def fixture(self):
        stamp = datetime(2001, 1, 1)
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('INSERT INTO todos (title,created_at,updated_at) VALUES (%s,%s,%s)',
                      (self.prefix, stamp, stamp))
            self.todos.append(c.lastrowid)
            c.execute('INSERT INTO scheduled_tasks (todo_id,start_at,end_at,reminder_at,created_at) '
                      'VALUES (%s,%s,%s,%s,%s)', (c.lastrowid, stamp, datetime(2001, 1, 1, 1), stamp, stamp))
            self.tasks.append(c.lastrowid)
        return self.tasks[-1], 'reminder:' + str(self.tasks[-1])

    def snapshot(self, task):
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('SELECT * FROM scheduled_tasks WHERE id=%s', (task,))
            row = c.fetchone()
            c.execute('SELECT * FROM sent_reminders WHERE scheduled_task_id=%s', (task,))
            return row, list(c.fetchall())

    def ack(self, task, key, suffix, **kwargs):
        return self.agent.ack_reminder(self.prefix + suffix, task, key,
                                       now='2001-01-01T08:00:00+08:00', **kwargs)

    def cleanup_records(self):
        with db.get_conn() as conn, conn.cursor() as c:
            for task in self.tasks:
                c.execute('DELETE FROM sent_reminders WHERE scheduled_task_id=%s', (task,))
                c.execute('DELETE FROM scheduled_tasks WHERE id=%s', (task,))
            for todo in self.todos:
                c.execute('DELETE FROM todos WHERE id=%s', (todo,))
        for request_id in self.requests:
            sql_executor._cache.pop(request_id, None)

    def test_success_duplicate_and_late_failure_preserve_success(self):
        task, key = self.fixture()
        result = self.ack(task, key, '-sent')
        self.assertTrue(result['success'], result)
        first = self.snapshot(task)
        row, sent = first
        self.assertEqual((row['reminder_status'], row['reminder_sent'], row['reminder_attempt_count']), ('SENT', 1, 1))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['idempotency_key'], key)
        self.assertEqual(sent[0]['sent_at'], datetime(2001, 1, 1))
        self.assertTrue(self.ack(task, key, '-sent')['success'])
        # 清除缓存模拟新进程的确认；唯一键和行锁须保持幂等。
        sql_executor._cache.pop(self.prefix + '-sent', None)
        self.assertTrue(self.ack(task, key, '-duplicate')['success'])
        self.assertTrue(self.ack(task, key, '-late', status='FAILED', error='迟到的失败')['success'])
        self.assertEqual(self.snapshot(task), first)
        conflict = self.ack(task, 'wrong-key', '-bad-key')
        self.assertEqual(conflict['error']['code'], 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(self.snapshot(task), first)

    def test_failure_remains_pollable_then_success(self):
        task, key = self.fixture()
        failed = self.ack(task, key, '-failed', status='FAILED', error='通知失败')
        self.assertTrue(failed['success'], failed)
        row, sent = self.snapshot(task)
        self.assertEqual((row['reminder_status'], row['reminder_sent'], row['reminder_error']), ('FAILED', 0, '通知失败'))
        self.assertEqual(sent, [])
        self.assertTrue(self.ack(task, key, '-failed', status='FAILED', error='通知失败')['success'])
        self.assertEqual(self.snapshot(task)[0]['reminder_attempt_count'], 1)
        polled = self.agent.poll_reminders(self.prefix + '-poll', now='2001-01-01T08:00:00+08:00')
        self.assertTrue(polled['success'], polled)
        self.assertIn(task, [r['scheduled_task_id'] for r in polled['reminders']])
        self.assertTrue(self.ack(task, key, '-retry')['success'])
        row, sent = self.snapshot(task)
        self.assertEqual((row['reminder_status'], row['reminder_attempt_count'], row['reminder_error']), ('SENT', 2, None))
        self.assertEqual(len(sent), 1)

    def test_unique_insert_failure_rolls_back_status_update(self):
        task, key = self.fixture()
        other, _ = self.fixture()
        with db.get_conn() as conn, conn.cursor() as c:
            c.execute('INSERT INTO sent_reminders (scheduled_task_id,sent_at,idempotency_key) VALUES (%s,%s,%s)',
                      (other, datetime(2001, 1, 1), key))
        before = self.snapshot(task)
        failed = self.ack(task, key, '-rollback')
        self.assertEqual(failed['error']['code'], 'INTERNAL_ERROR')
        self.assertFalse(failed['retryable'])
        self.assertEqual(self.snapshot(task), before)


if __name__ == '__main__':
    unittest.main()
