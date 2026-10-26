"""占用查询模板与 Agent 使用的确定性空档计算；不访问数据库。"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import config


def query_metadata(payload, now):
    zone = ZoneInfo(payload.get('timezone', 'Asia/Shanghai'))
    first = date.fromisoformat(str(payload['date']))
    last = date.fromisoformat(str(payload.get('end_date', payload['date'])))
    today = now.astimezone(zone).date()
    if not today <= first <= last < today + timedelta(days=config.SCHEDULE_HORIZON_DAYS):
        raise ValueError('查询日期必须在配置的排期范围内')
    duration = payload.get('duration_min', 30)
    if isinstance(duration, bool) or not isinstance(duration, int) or not 5 <= duration <= 1440:
        raise ValueError('duration_min 必须是 5 到 1440 的整数')
    deadline = payload.get('deadline')
    if deadline:
        deadline = datetime.fromisoformat(str(deadline).replace('Z', '+00:00'))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=zone)
        deadline = deadline.astimezone(zone)
    return dict(date=first, end_date=last, duration_min=duration, zone=zone, deadline=deadline)


def occupancy_statements(metadata):
    zone = metadata['zone']
    start = datetime.combine(metadata['date'], time(), zone)
    end = datetime.combine(metadata['end_date'] + timedelta(days=1), time(), zone)
    utc = lambda dt: dt.astimezone(ZoneInfo('UTC')).replace(tzinfo=None).isoformat(sep=' ')
    return [
        {'sql': 'SELECT start_at,end_at FROM scheduled_tasks WHERE status=%s AND done=%s AND start_at < %s AND end_at > %s',
         'params': ['ACTIVE', 0, utc(end), utc(start)]},
        {'sql': 'SELECT event_date,start_time,end_time FROM calendar_events WHERE event_date >= %s AND event_date <= %s',
         'params': [metadata['date'].isoformat(), metadata['end_date'].isoformat()]},
    ]


def compute_slots(metadata, results, now):
    zone = metadata['zone']
    def utc_datetime(value):
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo('UTC'))).astimezone(zone)
    def local_time(value):
        if isinstance(value, timedelta):
            return (datetime.min + value).time()
        return value if isinstance(value, time) else time.fromisoformat(value)
    occupied = []
    for result in results:
        for row in result.get('rows', []):
            if 'start_at' in row:
                occupied.append((utc_datetime(row['start_at']), utc_datetime(row['end_at'])))
            else:
                day = row['event_date']
                day = day if isinstance(day, date) else date.fromisoformat(day)
                occupied.append((datetime.combine(day, local_time(row['start_time']), zone),
                                 datetime.combine(day, local_time(row['end_time']), zone)))
    # 合并重叠及相邻占用，避免重复扫描同一段。
    merged = []
    for start, end in sorted(occupied):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    slots = []
    for offset in range((metadata['end_date'] - metadata['date']).days + 1):
        day = metadata['date'] + timedelta(days=offset)
        for sh, sm, eh, em in sorted(config.WORK_HOURS):
            cursor = max(datetime.combine(day, time(sh, sm), zone), now.astimezone(zone))
            window_end = datetime.combine(day, time(eh, em), zone)
            if metadata['deadline']:
                window_end = min(window_end, metadata['deadline'])
            if cursor.minute % 5 or cursor.second or cursor.microsecond:
                cursor = (cursor + timedelta(minutes=5 - cursor.minute % 5)).replace(second=0, microsecond=0)
            while cursor + timedelta(minutes=metadata['duration_min']) <= window_end:
                end = cursor + timedelta(minutes=metadata['duration_min'])
                if not any(start < end and finish > cursor for start, finish in merged):
                    slots.append(dict(start_at=cursor.replace(tzinfo=None).isoformat(sep=' '),
                                      end_at=end.replace(tzinfo=None).isoformat(sep=' '), timezone=str(zone)))
                cursor += timedelta(minutes=5)
    return slots
