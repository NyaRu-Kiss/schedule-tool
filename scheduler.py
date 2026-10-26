"""
日程效率工具 - 档期编排引擎

策略：按优先级 + 截止时间排序
  1. 取所有未排期、未完成的待办
  2. 排序：优先级数字越小越靠前 (1>2>3)；同优先级按截止时间升序；无截止时间排最后
  3. 逐个往 WORK_HOURS 时段里插：
     - 估算时长 (用户给 > 默认)
     - 从今天起往后扫 horizon_days 天的每个工作时段
     - 跳过已占用区间，找第一个空隙
  4. 若截止时间紧迫，会尽量往截止前插；实在赶不上也照常排，但记录告警
"""

from datetime import datetime, timedelta, time

import db
from config import (
    WORK_HOURS,
    DEFAULT_ESTIMATE_MINUTES,
    SCHEDULE_HORIZON_DAYS,
)


def _parse_dt(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s)


def _format_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def _work_slots_on(date):
    """返回某一天的可用工作时段 [(start_dt, end_dt), ...]"""
    slots = []
    for sh, sm, eh, em in WORK_HOURS:
        start = datetime.combine(date, time(sh, sm))
        end = datetime.combine(date, time(eh, em))
        slots.append((start, end))
    return slots


def _estimate(todo):
    if todo.get("estimate_min"):
        return todo["estimate_min"]
    return DEFAULT_ESTIMATE_MINUTES


def _sort_key(todo):
    """优先级 + 截止时间排序键"""
    p = todo.get("priority", 2) or 2
    dl = todo.get("deadline")
    # deadline IS NULL 在 SQL 里拍后面，这里用很大值
    dl_sort = _parse_dt(dl) or datetime(2099, 1, 1)
    return (p, dl_sort)


def _free_slot_in_day(date, duration_min, occupied):
    """
    在给定日期的工作时段里找一个长度 >= duration_min 的空隙
    occupied: [(start_dt, end_dt), ...] 当天已占用区间（已排好）
    返回 (start, end) 或 None
    """
    for slot_start, slot_end in _work_slots_on(date):
        # 跳过已过去的时段
        if slot_end <= datetime.now():
            continue
        # 如果当前时间在时段内，从当前整 5 分钟边界开始
        if datetime.now() > slot_start:
            slot_start = datetime.now()
            # 对齐到 5 分钟
            slot_start = slot_start.replace(
                minute=(slot_start.minute // 5) * 5,
                second=0, microsecond=0
            )

        # 把这个 slot 内所有 occupied 段按开始时间排
        conflicts = sorted(
            [(s, e) for s, e in occupied if e > slot_start and s < slot_end],
            key=lambda x: x[0]
        )

        cursor = slot_start
        for cs, ce in conflicts:
            if cs > cursor:
                gap = (cs - cursor).total_seconds() / 60
                if gap >= duration_min:
                    end = cursor + timedelta(minutes=duration_min)
                    return (cursor, end)
            cursor = max(cursor, ce)

        # 检查 slot 末尾还有没有空
        if cursor + timedelta(minutes=duration_min) <= slot_end:
            end = cursor + timedelta(minutes=duration_min)
            return (cursor, end)
    return None


def schedule_all():
    """
    把所有未排期待办插入档期。
    返回 dict: scheduled=[...], warnings=[...]
    """
    todos = db.get_unscheduled_todos()
    todos.sort(key=_sort_key)

    scheduled = []
    warnings = []

    # 取未来 horizon 天已排期，作为占用参考
    existing = db.list_schedule(days=SCHEDULE_HORIZON_DAYS)
    occupied = [
        (_parse_dt(r["start_at"]), _parse_dt(r["end_at"]))
        for r in existing
    ]
    if hasattr(db, "list_calendar_blocks"):
        occupied.extend(db.list_calendar_blocks(SCHEDULE_HORIZON_DAYS))

    today = datetime.now().date()

    for todo in todos:
        duration = _estimate(todo)
        deadline = _parse_dt(todo.get("deadline"))

        placed = None
        # 如果有 deadline，先尝试在 deadline 当天或之前找位置
        for offset in range(SCHEDULE_HORIZON_DAYS):
            date = today + timedelta(days=offset)
            if deadline and date > deadline.date():
                # 超过截止日还找不到，停止继续找
                if placed is None:
                    warnings.append(
                        f"⚠️ 「{todo['title']}」截止 {deadline.strftime('%m-%d')} 前已无空档，"
                        f"排在能找到的最早时段"
                    )
                break
            slot = _free_slot_in_day(date, duration, occupied)
            if slot:
                placed = slot
                break

        if not placed:
            # 再不限制 deadline 全范围扫一遍
            for offset in range(SCHEDULE_HORIZON_DAYS):
                date = today + timedelta(days=offset)
                slot = _free_slot_in_day(date, duration, occupied)
                if slot:
                    placed = slot
                    break

        if placed:
            start, end = placed
            db.insert_scheduled(todo["id"], start.isoformat(), end.isoformat())
            db.mark_todo_scheduled(todo["id"])
            occupied.append((start, end))
            occupied.sort(key=lambda x: x[0])
            scheduled.append({
                "todo_id": todo["id"],
                "title": todo["title"],
                "priority": todo["priority"],
                "start": _format_dt(start),
                "end": _format_dt(end),
                "deadline": todo.get("deadline"),
            })
        else:
            warnings.append(
                f"❌「{todo['title']}」在 {SCHEDULE_HORIZON_DAYS} 天内找不到 {duration} 分钟空档"
            )

    return {"scheduled": scheduled, "warnings": warnings}
