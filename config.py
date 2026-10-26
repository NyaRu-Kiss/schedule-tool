"""
日程效率工具 - 配置文件

所有配置可通过环境变量覆盖，也可写入 .env 文件由 setup.sh 加载。

核心配置：
  SCHEDULE_WEBHOOK_URL       — webhook 推送地址，留空则只打印控制台
  SCHEDULE_WEBHOOK_FORMAT    — 消息格式: generic | wecom | feishu | custom
  SCHEDULE_WEBHOOK_TIMEOUT   — 请求超时秒数，默认 8
  SCHEDULE_WEBHOOK_RETRY     — 失败重试次数，默认 3
  SCHEDULE_WEBHOOK_HEADERS   — 自定义请求头 JSON，如 '{"Authorization":"Bearer xxx"}'
  SCHEDULE_WEBHOOK_TEMPLATE  — 自定义消息体 Jinja2 模板（format=custom 时生效）

数据库和服务：
  SCHEDULE_DB_PATH           — SQLite 数据库路径
  SCHEDULE_HOST / PORT       — Flask 监听
"""

import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------- 加载 .env 文件 ----------

def _load_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

_load_env_file()


# ---------- 数据库 ----------

DB_PATH = os.getenv("SCHEDULE_DB_PATH", str(BASE_DIR / "schedule.db"))
DB_BACKEND = os.getenv("SCHEDULE_DB_BACKEND", "sqlite").lower()
DB_HOST = os.getenv("SCHEDULE_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("SCHEDULE_DB_PORT", "3306"))
DB_USER = os.getenv("SCHEDULE_DB_USER", "root")
DB_PASSWORD = os.getenv("SCHEDULE_DB_PASSWORD", "")
DB_NAME = os.getenv("SCHEDULE_DB_NAME", "agenda_tool")
# Agent -> backend 服务认证令牌；生产环境必须配置，空值时内部接口拒绝请求。
INTERNAL_SERVICE_TOKEN = os.getenv("SCHEDULE_INTERNAL_SERVICE_TOKEN", "")

# ---------- Flask ----------

HOST = os.getenv("SCHEDULE_HOST", "0.0.0.0")
PORT = int(os.getenv("SCHEDULE_PORT", "7800"))

# ---------- Webhook 推送 ----------

# 推送地址，留空则只打印控制台不实际推送
WEBHOOK_URL = os.getenv("SCHEDULE_WEBHOOK_URL", "")

# 消息格式:
#   generic  — 通用 JSON，body 直接是 {"text": "...", "items": [...]}，适配自建平台
#   wecom    — 企业微信群机器人格式 {"msgtype":"text","text":{"content":"..."}}
#   feishu   — 飞书自定义机器人格式 {"msg_type":"text","content":{"text":"..."}}
#   custom   — 使用 WEBHOOK_TEMPLATE 模板渲染
WEBHOOK_FORMAT = os.getenv("SCHEDULE_WEBHOOK_FORMAT", "generic")

# 请求超时（秒）
WEBHOOK_TIMEOUT = int(os.getenv("SCHEDULE_WEBHOOK_TIMEOUT", "8"))

# 失败重试次数（指数退避：2s, 4s, 8s...）
WEBHOOK_RETRY = int(os.getenv("SCHEDULE_WEBHOOK_RETRY", "3"))

# 自定义请求头（JSON 字符串）
# 例: '{"Authorization":"Bearer token123","X-Source":"schedule-tool"}'
WEBHOOK_HEADERS = os.getenv("SCHEDULE_WEBHOOK_HEADERS", "")

# 自定义消息体模板（format=custom 时生效）
# 使用 Python str.format 语法，可用变量: {text} {items_json} {count}
# 例: '{"event":"reminder","message":"{text}","count":{count}}'
WEBHOOK_TEMPLATE = os.getenv(
    "SCHEDULE_WEBHOOK_TEMPLATE",
    '{"event": "reminder", "message": "{text}", "count": {count}}',
)

# ---------- 提醒 ----------

# 提醒提前量（分钟）：到点前 N 分钟发第一条提醒
REMIND_LEAD_MINUTES = int(os.getenv("SCHEDULE_REMIND_LEAD_MINUTES", "5"))

# 扫描间隔（秒）
SCAN_INTERVAL_SECONDS = int(os.getenv("SCHEDULE_SCAN_INTERVAL_SECONDS", "30"))

# ---------- 编排 ----------

# 每日工作时段：编排待办时只往这些时段里插
# 格式 [(start_hour, start_min, end_hour, end_min), ...]
WORK_HOURS = [
    (9, 0, 12, 0),
    (14, 0, 18, 0),
    (19, 30, 21, 30),
]

# 未指定预估时长的待办，默认估时（分钟）
DEFAULT_ESTIMATE_MINUTES = int(os.getenv("SCHEDULE_DEFAULT_ESTIMATE_MINUTES", "30"))

# 编排时一次往后看多少天
SCHEDULE_HORIZON_DAYS = int(os.getenv("SCHEDULE_HORIZON_DAYS", "7"))


def get_webhook_config():
    """返回当前 webhook 配置摘要，供 /api/webhook/config 接口使用"""
    headers = {}
    if WEBHOOK_HEADERS:
        try:
            headers = json.loads(WEBHOOK_HEADERS)
        except json.JSONDecodeError:
            pass
    return {
        "url": WEBHOOK_URL[:40] + "..." if len(WEBHOOK_URL) > 40 else WEBHOOK_URL,
        "url_configured": bool(WEBHOOK_URL),
        "format": WEBHOOK_FORMAT,
        "timeout_sec": WEBHOOK_TIMEOUT,
        "retry_count": WEBHOOK_RETRY,
        "custom_headers": list(headers.keys()),
        "has_template": WEBHOOK_FORMAT == "custom",
    }
