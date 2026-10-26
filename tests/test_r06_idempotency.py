"""R06：独立进程重放、唯一键竞争及未提交连接中断的真实 MySQL 验收。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock

import db
import sql_executor
from agent import AgendaAgent
import test_t04_create as t04
import test_t09_ack as t09

set_value = t04.set_value


CHILD = r'''
import json, os, sys, time
from contextlib import contextmanager
from pathlib import Path
import db, sql_executor
payload = json.loads(sys.stdin.readline())
mode = sys.argv[1]
if mode == 'race':
    original = sql_executor._replay_created_schedule
    def replay(cursor, request_id, attempt):
        result = original(cursor, request_id, attempt)
        if result is None:
            Path(sys.argv[2], sys.argv[3]).touch()
            deadline = time.monotonic() + 10
            while len(list(Path(sys.argv[2]).iterdir())) < 2:
                if time.monotonic() > deadline:
                    raise RuntimeError('race barrier timeout')
                time.sleep(.01)
        return result
    sql_executor._replay_created_schedule = replay
elif mode == 'disconnect':
    original_conn = db.get_conn
    @contextmanager
    def disconnect_conn():
        with original_conn() as conn:
            with conn.cursor() as cursor:
                class Cursor:
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def __getattr__(self, name): return getattr(cursor, name)
                    def execute(self, sql, params):
                        result = cursor.execute(sql, params)
                        if sql.startswith('INSERT INTO todos') or sql.startswith('UPDATE scheduled_tasks'):
                            os._exit(73)
                        return result
                class Connection:
                    def cursor(self): return Cursor()
                yield Connection()
    db.get_conn = disconnect_conn
print(json.dumps(sql_executor.execute(payload)), flush=True)
'''


def child(payload, mode='normal'):
    result = subprocess.run([sys.executable, '-c', CHILD, mode], input=json.dumps(payload) + '\n',
                            text=True, capture_output=True, timeout=20,
                            cwd=Path(__file__).resolve().parents[1])
    if mode == 'disconnect':
        if result.returncode != 73:
            raise AssertionError((result.returncode, result.stdout, result.stderr))
        return None
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ReplayUnitTests(unittest.TestCase):
    def test_replay_uses_persisted_ids_and_times(self):
        cursor = Mock()
        cursor.fetchall.return_value = [dict(todo_id=12, scheduled_task_id=34,
            start_at=datetime(2040, 1, 1), end_at=datetime(2040, 1, 1, 0, 30),
            reminder_at=None, timezone='UTC', auto_scheduled=1)]
        result = sql_executor._replay_created_schedule(cursor, 'r06', 2)
        self.assertTrue(result['idempotent_replay'])
        self.assertEqual(result['schedule']['scheduled_task_id'], 34)
        self.assertEqual(result['schedule']['start_at'], '2040-01-01 00:00:00')
        self.assertTrue(result['schedule']['auto_scheduled'])
        self.assertIsNone(result['schedule']['reminder_at'])
        self.assertEqual([r['last_insert_id'] for r in result['results']], [12, 34])
        cursor.fetchall.return_value = []
        self.assertIsNone(sql_executor._replay_created_schedule(cursor, 'r06', 1))


class CreationMySQLTests(t04.CreateMySQLTests):
    # 复用 T04 的认证、UTC、冲突与第二条 INSERT 回滚回归。
    def test_new_process_replays_original_even_if_candidate_changes(self):
        for auto in (False, True):
            with self.subTest(auto=auto):
                payload = self.payload('-restart-' + str(auto))
                if auto:
                    payload['operation'] = 'AUTO_CREATE_SCHEDULE'
                    set_value(payload, 0, 'auto_scheduled', 1)
                    set_value(payload, 1, 'schedule_source', 'AUTO')
                    set_value(payload, 1, 'start_at', '2040-10-10T16:00:00+08:00')
                    set_value(payload, 1, 'end_at', '2040-10-10T16:30:00+08:00')
                first = child(payload)
                self.assertTrue(first['success'], first)
                changed = copy.deepcopy(payload)
                set_value(changed, 1, 'start_at', '2040-10-10T17:00:00+08:00')
                set_value(changed, 1, 'end_at', '2040-10-10T17:30:00+08:00')
                replay = child(changed)
                self.assertTrue(replay['success'], replay)
                self.assertTrue(replay['idempotent_replay'])
                self.assertEqual(replay['schedule'], first['schedule'])
                self.assertEqual(replay['results'], first['results'])
                self.assertEqual(len(self.rows(payload['request_id'])), 1)

    def test_two_processes_same_request_commit_one_schedule(self):
        payload = self.payload('-race')
        with tempfile.TemporaryDirectory(prefix='r06-barrier-') as barrier:
            processes = [subprocess.Popen([sys.executable, '-c', CHILD, 'race', barrier, str(i)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=Path(__file__).resolve().parents[1]) for i in range(2)]
            try:
                for process in processes:
                    process.stdin.write(json.dumps(payload) + '\n')
                    process.stdin.flush()
                results = []
                for process in processes:
                    out, err = process.communicate(timeout=20)
                    self.assertEqual(process.returncode, 0, err)
                    results.append(json.loads(out))
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
            self.assertTrue(all(r['success'] for r in results), results)
            self.assertEqual(results[0]['schedule'], results[1]['schedule'])
            self.assertEqual(sum(bool(r.get('idempotent_replay')) for r in results), 1)
            self.assertEqual(len(self.rows(payload['request_id'])), 1)

    def test_disconnect_after_first_insert_rolls_back_then_retry_succeeds(self):
        payload = self.payload('-disconnect')
        child(payload, 'disconnect')
        with db.get_conn() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM todos WHERE request_id=%s', (payload['request_id'],))
            self.assertEqual(cursor.fetchone()['n'], 0)
        self.assertTrue(child(payload)['success'])
        self.assertEqual(len(self.rows(payload['request_id'])), 1)


class ReminderMySQLTests(t09.AckMySQLTests):
    # 复用 T09 的重复成功确认、失败后重试及唯一键故障原子回滚。
    def ack_payload(self, task, key, suffix, status='SENT'):
        backend = Mock(return_value={'success': True})
        AgendaAgent(backend).ack_reminder(self.prefix + suffix, task, key,
            status=status, now='2001-01-01T08:00:00+08:00', error='发送失败' if status == 'FAILED' else None)
        return backend.call_args.args[0]

    def test_success_confirmation_survives_new_process_and_late_failure(self):
        task, key = self.fixture()
        sent = self.ack_payload(task, key, '-process-sent')
        self.assertTrue(child(sent)['success'])
        first = self.snapshot(task)
        replay = child(sent)
        self.assertTrue(replay['idempotent_replay'])
        self.assertTrue(child(self.ack_payload(task, key, '-late', 'FAILED'))['success'])
        self.assertEqual(self.snapshot(task), first)
        self.assertEqual(len(first[1]), 1)

    def test_disconnect_after_update_preserves_pending_then_retry_succeeds(self):
        task, key = self.fixture()
        sent = self.ack_payload(task, key, '-disconnect')
        first = self.snapshot(task)
        child(sent, 'disconnect')
        self.assertEqual(self.snapshot(task), first)
        self.assertTrue(child(sent)['success'])
        row, records = self.snapshot(task)
        self.assertEqual(row['reminder_status'], 'SENT')
        self.assertEqual(row['reminder_attempt_count'], 1)
        self.assertEqual(len(records), 1)


if __name__ == '__main__':
    unittest.main()
