"""
日程效率工具 - 数据库层

表结构：
  todos            用户添加的待办项（原始记录）
  scheduled_tasks  编排结果（待办被排进的具体时段）
  sent_reminders   已发送的提醒记录（去重用）
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import DB_PATH, DB_BACKEND, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


def _display_local(value, timezone):
    """Convert a UTC database datetime to the schedule's display timezone."""
    try:
        zone = ZoneInfo(str(timezone or "Asia/Shanghai"))
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Asia/Shanghai")
    return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,                  -- 待办标题
    priority        INTEGER NOT NULL DEFAULT 2,     -- 优先级 1=高 2=中 3=低
    deadline        TEXT,                            -- 截止时间 ISO 格式,可为空
    estimate_min    INTEGER,                         -- 预估时长(分钟),可为空
    scheduled       INTEGER NOT NULL DEFAULT 0,      -- 是否已被编排 0/1
    done            INTEGER NOT NULL DEFAULT 0,      -- 是否完成 0/1
    source          TEXT,                             -- 来源: workbuddy / cli / api
    raw_input       TEXT,                             -- 用户原始输入
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id         INTEGER NOT NULL,
    start_at        TEXT NOT NULL,                   -- 排期开始 ISO 时间
    end_at          TEXT NOT NULL,                   -- 排期结束 ISO 时间
    reminder_sent   INTEGER NOT NULL DEFAULT 0,      -- 是否已发提醒
    done            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (todo_id) REFERENCES todos(id)
);

CREATE TABLE IF NOT EXISTS sent_reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_task_id INTEGER NOT NULL,
    sent_at         TEXT NOT NULL,
    UNIQUE(scheduled_task_id)                        -- 每个 scheduled_task 只提醒一次
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,                   -- reminder / test / manual
    url             TEXT,                              -- 推送目标 URL
    payload         TEXT,                              -- 请求体 JSON
    status_code     INTEGER,                          -- 响应状态码
    response_body   TEXT,                              -- 响应体（截断）
    success         INTEGER NOT NULL DEFAULT 0,      -- 0=失败 1=成功
    error           TEXT,                              -- 错误信息
    retry_count     INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,                          -- 耗时毫秒
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_todos_scheduled ON todos(scheduled);
CREATE INDEX IF NOT EXISTS idx_todos_done ON todos(done);
CREATE INDEX IF NOT EXISTS idx_sched_start ON scheduled_tasks(start_at);
CREATE INDEX IF NOT EXISTS idx_sched_reminder ON scheduled_tasks(reminder_sent);
CREATE INDEX IF NOT EXISTS idx_webhook_logs_created ON webhook_logs(created_at);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ---------- todos CRUD ----------

def insert_todo(title, priority=2, deadline=None, estimate_min=None,
                source="cli", raw_input=None):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO todos
               (title, priority, deadline, estimate_min, scheduled, done,
                source, raw_input, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?)""",
            (title, priority, deadline, estimate_min, source, raw_input, now, now),
        )
        return cur.lastrowid


def list_todos(only_undone=False):
    sql = "SELECT * FROM todos"
    if only_undone:
        sql += " WHERE done = 0"
    sql += " ORDER BY priority ASC, deadline IS NULL, deadline ASC, created_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def mark_todo_done(todo_id):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE todos SET done=1, updated_at=? WHERE id=?", (now, todo_id)
        )
        conn.execute(
            "UPDATE scheduled_tasks SET done=1 WHERE todo_id=?", (todo_id,)
        )


def get_unscheduled_todos():
    sql = """SELECT * FROM todos
             WHERE scheduled = 0 AND done = 0
             ORDER BY priority ASC, deadline IS NULL, deadline ASC"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def mark_todo_scheduled(todo_id):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE todos SET scheduled=1, updated_at=? WHERE id=?", (now, todo_id)
        )


# ---------- scheduled_tasks ----------

def insert_scheduled(todo_id, start_at, end_at):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO scheduled_tasks
               (todo_id, start_at, end_at, reminder_sent, done, created_at)
               VALUES (?, ?, ?, 0, 0, ?)""",
            (todo_id, start_at, end_at, now),
        )
        return cur.lastrowid


def list_schedule(days=3):
    """返回未来 days 天的排期"""
    from datetime import timedelta
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    sql = """SELECT s.*, t.title, t.priority, t.deadline
             FROM scheduled_tasks s
             JOIN todos t ON s.todo_id = t.id
             WHERE s.start_at >= ? AND s.start_at < ? AND s.done = 0
             ORDER BY s.start_at"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (start.isoformat(), end.isoformat())).fetchall()]


def get_pending_reminders(lead_minutes=5):
    """返回需要发提醒的排期：未提醒过、start_at <= now + lead"""
    from datetime import timedelta
    threshold = (datetime.now() + timedelta(minutes=lead_minutes)).isoformat()
    sql = """SELECT s.*, t.title, t.priority
             FROM scheduled_tasks s
             JOIN todos t ON s.todo_id = t.id
             WHERE s.reminder_sent = 0 AND s.done = 0
               AND s.start_at <= ?
             ORDER BY s.start_at"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (threshold,)).fetchall()]


def mark_reminder_sent(scheduled_task_id):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_tasks SET reminder_sent=1 WHERE id=?",
            (scheduled_task_id,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO sent_reminders (scheduled_task_id, sent_at) VALUES (?, ?)",
            (scheduled_task_id, now),
        )


# ---------- webhook_logs ----------

def insert_webhook_log(event_type, url, payload, status_code, response_body,
                       success, error, retry_count, duration_ms):
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO webhook_logs
               (event_type, url, payload, status_code, response_body,
                success, error, retry_count, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, url, payload, status_code,
             (response_body or "")[:500],
             success, error, retry_count, duration_ms, now),
        )
        return cur.lastrowid


def list_webhook_logs(limit=20):
    sql = """SELECT * FROM webhook_logs
             ORDER BY created_at DESC
             LIMIT ?"""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]


# MySQL backend used when the tool is shared with the calendar UI. The SQLite
# implementation above remains the default for local and backwards-compatible use.
if DB_BACKEND == "mysql":
    import pymysql
    from pymysql.cursors import DictCursor

    MYSQL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS todos (
      id INT PRIMARY KEY AUTO_INCREMENT, title VARCHAR(500) NOT NULL,
      priority INT NOT NULL DEFAULT 2, deadline DATETIME NULL,
      estimate_min INT NULL, scheduled TINYINT NOT NULL DEFAULT 0,
      done TINYINT NOT NULL DEFAULT 0, source VARCHAR(100), raw_input TEXT,
      created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    );
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
      id INT PRIMARY KEY AUTO_INCREMENT, todo_id INT NOT NULL,
      start_at DATETIME NOT NULL, end_at DATETIME NOT NULL,
      reminder_sent TINYINT NOT NULL DEFAULT 0, done TINYINT NOT NULL DEFAULT 0,
      created_at DATETIME NOT NULL, FOREIGN KEY (todo_id) REFERENCES todos(id)
    );
    CREATE TABLE IF NOT EXISTS sent_reminders (
      id INT PRIMARY KEY AUTO_INCREMENT, scheduled_task_id INT NOT NULL UNIQUE,
      sent_at DATETIME NOT NULL
    );
    CREATE TABLE IF NOT EXISTS webhook_logs (
      id INT PRIMARY KEY AUTO_INCREMENT, event_type VARCHAR(50) NOT NULL,
      url TEXT, payload LONGTEXT, status_code INT NULL, response_body TEXT,
      success TINYINT NOT NULL DEFAULT 0, error TEXT, retry_count INT NOT NULL DEFAULT 0,
      duration_ms INT NULL, created_at DATETIME NOT NULL
    );
    CREATE TABLE IF NOT EXISTS event_types (
      id VARCHAR(64) PRIMARY KEY, name VARCHAR(64) NOT NULL, color VARCHAR(16) NOT NULL,
      sort_order INT NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS calendar_events (
      id VARCHAR(64) PRIMARY KEY, type_id VARCHAR(64) NOT NULL, title VARCHAR(255) NOT NULL,
      event_date DATE NOT NULL, start_time TIME NOT NULL, end_time TIME NOT NULL,
      note VARCHAR(1000) NULL
    );
    CREATE TABLE IF NOT EXISTS goals (
      id VARCHAR(64) PRIMARY KEY, title VARCHAR(255) NOT NULL, description VARCHAR(1000),
      start_date DATE NOT NULL, end_date DATE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS milestones (
      id VARCHAR(64) PRIMARY KEY, goal_id VARCHAR(64) NOT NULL, title VARCHAR(255) NOT NULL,
      milestone_date DATE NOT NULL, completed TINYINT NOT NULL DEFAULT 0,
      FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
    );
    """

    @contextmanager
    def get_conn():
        conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                               password=DB_PASSWORD, database=DB_NAME,
                               cursorclass=DictCursor, autocommit=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _fetch(sql, args=()):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())

    def _json_rows(rows):
        return [{key: value.isoformat() if isinstance(value, datetime) else value
                 for key, value in row.items()} for row in rows]

    def init_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                for statement in MYSQL_SCHEMA.split(';'):
                    if statement.strip(): cur.execute(statement)
                cur.execute("SELECT COUNT(*) AS n FROM event_types")
                if cur.fetchone()['n'] == 0:
                    cur.executemany(
                        "INSERT INTO event_types (id,name,color,sort_order) VALUES (%s,%s,%s,%s)",
                        [('meeting','会议','#3b82f6',1), ('on-site','现场活动','#f97316',2),
                         ('external','外部项目','#8b5cf6',3), ('work','工作','#10b981',4),
                         ('social','社交','#ec4899',5), ('dating','恋爱','#ef4444',6)])

    def insert_todo(title, priority=2, deadline=None, estimate_min=None, source="cli", raw_input=None):
        now = datetime.now().replace(microsecond=0)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO todos (title,priority,deadline,estimate_min,source,raw_input,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (title,priority,deadline,estimate_min,source,raw_input,now,now))
                return cur.lastrowid

    def list_todos(only_undone=False):
        return _json_rows(_fetch("SELECT * FROM todos" + (" WHERE done=0" if only_undone else "") + " ORDER BY priority ASC, deadline IS NULL, deadline ASC, created_at DESC"))

    def mark_todo_done(todo_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE todos SET done=1,updated_at=%s WHERE id=%s", (datetime.now(),todo_id))
                cur.execute("UPDATE scheduled_tasks SET done=1 WHERE todo_id=%s", (todo_id,))

    def get_unscheduled_todos():
        return _json_rows(_fetch("SELECT * FROM todos WHERE scheduled=0 AND done=0 ORDER BY priority ASC, deadline IS NULL, deadline ASC"))

    def mark_todo_scheduled(todo_id):
        with get_conn() as conn:
            with conn.cursor() as cur: cur.execute("UPDATE todos SET scheduled=1,updated_at=%s WHERE id=%s", (datetime.now(),todo_id))

    def insert_scheduled(todo_id, start_at, end_at):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO scheduled_tasks (todo_id,start_at,end_at,created_at) VALUES (%s,%s,%s,%s)", (todo_id,start_at,end_at,datetime.now()))
                return cur.lastrowid

    def list_schedule(days=3):
        from datetime import timedelta
        start=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0); end=start+timedelta(days=days)
        return _json_rows(_fetch("SELECT s.*,t.title,t.priority,t.deadline FROM scheduled_tasks s JOIN todos t ON s.todo_id=t.id WHERE s.start_at >= %s AND s.start_at < %s AND s.done=0 ORDER BY s.start_at", (start,end)))

    def get_pending_reminders(lead_minutes=5):
        from datetime import timedelta
        return _json_rows(_fetch("SELECT s.*,t.title,t.priority FROM scheduled_tasks s JOIN todos t ON s.todo_id=t.id WHERE s.reminder_sent=0 AND s.done=0 AND s.start_at <= %s ORDER BY s.start_at", (datetime.now()+timedelta(minutes=lead_minutes),)))

    def mark_reminder_sent(scheduled_task_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE scheduled_tasks SET reminder_sent=1 WHERE id=%s", (scheduled_task_id,))
                cur.execute("INSERT IGNORE INTO sent_reminders (scheduled_task_id,sent_at) VALUES (%s,%s)", (scheduled_task_id,datetime.now()))

    def insert_webhook_log(event_type,url,payload,status_code,response_body,success,error,retry_count,duration_ms):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO webhook_logs (event_type,url,payload,status_code,response_body,success,error,retry_count,duration_ms,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (event_type,url,payload,status_code,(response_body or '')[:500],success,error,retry_count,duration_ms,datetime.now()))
                return cur.lastrowid

    def list_webhook_logs(limit=20):
        return _json_rows(_fetch("SELECT * FROM webhook_logs ORDER BY created_at DESC LIMIT %s", (limit,)))

    def list_event_types():
        return _fetch("SELECT id,name,color FROM event_types ORDER BY sort_order,id")

    def create_event_type(event_id, name, color):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM event_types")
                order = cur.fetchone()['n']
                cur.execute("INSERT INTO event_types (id,name,color,sort_order) VALUES (%s,%s,%s,%s)", (event_id,name,color,order))
        return {'id': event_id, 'name': name, 'color': color}

    def update_event_type(event_id, name, color):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE event_types SET name=%s,color=%s WHERE id=%s", (name,color,event_id))
                cur.execute("SELECT id FROM event_types WHERE id=%s", (event_id,))
                if not cur.fetchone(): return None
        return {'id': event_id, 'name': name, 'color': color}

    def delete_event_type(event_id):
        if event_id == 'work': return False
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM calendar_events WHERE type_id=%s", (event_id,))
                if cur.fetchone()['n'] > 0: return False
                cur.execute("DELETE FROM event_types WHERE id=%s", (event_id,))
        return True

    def list_calendar_blocks(days):
        from datetime import timedelta
        start = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        end = start + timedelta(days=days)
        rows = _fetch("SELECT event_date,start_time,end_time FROM calendar_events WHERE event_date >= %s AND event_date < %s", (start.date(),end.date()))
        return [(datetime.combine(row['event_date'], (datetime.min + row['start_time']).time()),
                 datetime.combine(row['event_date'], (datetime.min + row['end_time']).time())) for row in rows]

    def list_calendar_events():
        rows = _fetch("SELECT id,type_id,title,event_date,start_time,end_time,note FROM calendar_events ORDER BY event_date,start_time")
        for row in rows:
            row['date'] = str(row.pop('event_date')); row['typeId'] = row.pop('type_id')
            row['startTime'] = (datetime.min + row.pop('start_time')).strftime('%H:%M')
            row['endTime'] = (datetime.min + row.pop('end_time')).strftime('%H:%M')
            if not row.get('note'): row.pop('note', None)
        # Automatically scheduled todos appear in the same calendar view.
        for row in _fetch("SELECT s.id,s.start_at,s.end_at,s.timezone,t.timezone AS todo_timezone,t.title FROM scheduled_tasks s JOIN todos t ON t.id=s.todo_id WHERE s.done=0 ORDER BY s.start_at"):
            timezone = row.get('timezone') or row.get('todo_timezone') or 'Asia/Shanghai'
            start = _display_local(row['start_at'], timezone)
            end = _display_local(row['end_at'], timezone)
            rows.append({'id': 'todo-' + str(row['id']), 'typeId': 'work', 'title': row['title'],
                         'date': str(start.date()), 'startTime': str(start.time())[:5],
                         'endTime': str(end.time())[:5], 'note': '自动排期待办'})
        return rows

    def create_calendar_event(event):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO calendar_events (id,type_id,title,event_date,start_time,end_time,note) VALUES (%s,%s,%s,%s,%s,%s,%s)", (event['id'],event['typeId'],event['title'],event['date'],event['startTime'],event['endTime'],event.get('note')))
        return event

    def update_calendar_event(event_id, event):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE calendar_events SET type_id=%s,title=%s,event_date=%s,start_time=%s,end_time=%s,note=%s WHERE id=%s", (event['typeId'],event['title'],event['date'],event['startTime'],event['endTime'],event.get('note'),event_id))
                cur.execute("SELECT id FROM calendar_events WHERE id=%s", (event_id,))
                if not cur.fetchone(): return None
        return dict(event, id=event_id)

    def delete_calendar_event(event_id):
        if str(event_id).startswith('todo-'): return False
        with get_conn() as conn:
            with conn.cursor() as cur: cur.execute("DELETE FROM calendar_events WHERE id=%s", (event_id,))
        return True

    def list_goals():
        goals = _fetch("SELECT id,title,description,start_date,end_date FROM goals ORDER BY start_date")
        milestones = _fetch("SELECT id,goal_id,title,milestone_date,completed FROM milestones ORDER BY milestone_date")
        for goal in goals:
            goal['startDate']=str(goal.pop('start_date')); goal['endDate']=str(goal.pop('end_date'))
            goal['milestones']=[{'id':m['id'],'title':m['title'],'date':str(m['milestone_date']),'completed':bool(m['completed'])} for m in milestones if m['goal_id']==goal['id']]
            if not goal.get('description'): goal.pop('description',None)
        return goals

    def save_goal(goal):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO goals (id,title,description,start_date,end_date) VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE title=VALUES(title),description=VALUES(description),start_date=VALUES(start_date),end_date=VALUES(end_date)", (goal['id'],goal['title'],goal.get('description'),goal['startDate'],goal['endDate']))
                cur.execute("DELETE FROM milestones WHERE goal_id=%s", (goal['id'],))
                cur.executemany("INSERT INTO milestones (id,goal_id,title,milestone_date,completed) VALUES (%s,%s,%s,%s,%s)", [(m['id'],goal['id'],m['title'],m['date'],1 if m.get('completed') else 0) for m in goal.get('milestones',[])])
        return goal

    def delete_goal(goal_id):
        with get_conn() as conn:
            with conn.cursor() as cur: cur.execute("DELETE FROM goals WHERE id=%s", (goal_id,))
