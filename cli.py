"""
日程效率工具 - 命令行入口

用法:
  python cli.py add "写周报" -p 2 -d "2026-10-08 18:00" -e 60
  python cli.py list
  python cli.py schedule          # 手动编排未排期待办
  python cli.py today             # 看今天档期
  python cli.py done <todo_id>
  python cli.py scan              # 立即扫描一次提醒
  python cli.py server            # 启动 Flask + 扫描线程
"""

import argparse
import sys
from datetime import datetime

import db
import scheduler
from remind import scan_and_remind


def cmd_add(args):
    deadline = None
    if args.deadline:
        try:
            deadline = args.deadline.replace(" ", "T")
            datetime.fromisoformat(deadline)
        except ValueError:
            print(f"❌ 截止时间格式错误: {args.deadline}，应为 YYYY-MM-DDTHH:MM")
            sys.exit(1)

    todo_id = db.insert_todo(
        title=args.title,
        priority=args.priority,
        deadline=deadline,
        estimate_min=args.estimate,
        source="cli",
        raw_input=args.title,
    )
    print(f"✅ 已添加 (id={todo_id}): {args.title}")

    # 添加后自动编排
    result = scheduler.schedule_all()
    for s in result["scheduled"]:
        if s["todo_id"] == todo_id:
            print(f"   排期: {s['start']} → {s['end']}")
    for w in result["warnings"]:
        print(w)


def cmd_list(args):
    todos = db.list_todos(only_undone=args.undone)
    if not todos:
        print("(空)")
        return
    print(f"{'ID':>4}  {'P':>1}  {'截止':<16}  {'估时':>4}  {'标题'}")
    print("-" * 70)
    for t in todos:
        dl = (t["deadline"] or "")[:16].replace("T", " ")
        est = f"{t['estimate_min']}m" if t["estimate_min"] else "-"
        flag = "✓" if t["scheduled"] else "·"
        print(f"{t['id']:>4}  {t['priority']}  {dl:<16}  {est:>4}  {flag} {t['title']}")


def cmd_schedule(args):
    result = scheduler.schedule_all()
    if not result["scheduled"]:
        print("没有需要新排期的待办")
        return
    print(f"本次编排 {len(result['scheduled'])} 项:")
    for s in result["scheduled"]:
        print(f"  [{s['priority']}] {s['title']}")
        print(f"      {s['start']} → {s['end']}")
    for w in result["warnings"]:
        print(w)


def cmd_today(args):
    items = db.list_schedule(days=1)
    if not items:
        print("今天没有排期")
        return
    print("今天档期:")
    for s in items:
        st = s["start_at"][:16].replace("T", " ")
        et = s["end_at"][11:16]
        p = {1: "高", 2: "中", 3: "低"}.get(s.get("priority"), "中")
        print(f"  {st} - {et}  [{p}] {s['title']}")


def cmd_done(args):
    db.mark_todo_done(args.todo_id)
    print(f"✅ 已完成 todo {args.todo_id}")


def cmd_scan(args):
    n = scan_and_remind()
    print(f"本次推送 {n} 条提醒")


def cmd_server(args):
    from app import main
    main()


def build_parser():
    p = argparse.ArgumentParser(description="日程效率工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="添加待办")
    a.add_argument("title", help="待办标题")
    a.add_argument("-p", "--priority", type=int, default=2, choices=[1, 2, 3],
                   help="优先级 1=高 2=中 3=低")
    a.add_argument("-d", "--deadline", help="截止时间 YYYY-MM-DDTHH:MM")
    a.add_argument("-e", "--estimate", type=int, help="预估时长(分钟)")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="列出待办")
    l.add_argument("--undone", action="store_true", help="只列未完成")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("schedule", help="编排未排期待办")
    s.set_defaults(func=cmd_schedule)

    t = sub.add_parser("today", help="查看今天档期")
    t.set_defaults(func=cmd_today)

    d = sub.add_parser("done", help="标记完成")
    d.add_argument("todo_id", type=int)
    d.set_defaults(func=cmd_done)

    sc = sub.add_parser("scan", help="立即扫描提醒")
    sc.set_defaults(func=cmd_scan)

    sv = sub.add_parser("server", help="启动 Flask 服务")
    sv.set_defaults(func=cmd_server)

    return p


def main():
    db.init_db()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()