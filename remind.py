"""
日程效率工具 - 通用 Webhook 推送模块

支持 4 种消息格式：
  generic  — 通用 JSON，body 为 {"event","text","count","items"}，适配自建平台（默认）
  wecom    — 企业微信群机器人格式 {"msgtype":"text","text":{"content":"..."}}
  feishu   — 飞书自定义机器人格式 {"msg_type":"text","content":{"text":"..."}}
  custom   — 使用 WEBHOOK_TEMPLATE 模板渲染（Python str.format 语法）

特性：
  - 指数退避重试（WEBHOOK_RETRY 次）
  - 每次推送落库到 webhook_logs 表
  - 未配置 URL 时只打印控制台
"""

import json
import logging
import time

import requests

import db
from config import (
    WEBHOOK_URL,
    WEBHOOK_FORMAT,
    WEBHOOK_TIMEOUT,
    WEBHOOK_RETRY,
    WEBHOOK_HEADERS,
    WEBHOOK_TEMPLATE,
    REMIND_LEAD_MINUTES,
)

log = logging.getLogger("remind")


# ---------- 消息格式化 ----------

def _format_text(items):
    """把多条待提醒事项拼成纯文本"""
    lines = ["⏰ 日程提醒", ""]
    for it in items:
        title = it["title"]
        start_value = it["start_at"]
        start = start_value.isoformat(sep=" ")[:16] if hasattr(start_value, "isoformat") else start_value[:16].replace("T", " ")
        p = {1: "高", 2: "中", 3: "低"}.get(it.get("priority"), "中")
        lines.append(f"• [{p}] {title}")
        lines.append(f"  开始: {start}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_payload(text, items, fmt=None):
    """
    根据消息格式构造请求体。
    返回 (dict, str)：(payload_dict, payload_json_str)
    """
    fmt = fmt or WEBHOOK_FORMAT
    count = len(items)

    if fmt == "wecom":
        payload = {"msgtype": "text", "text": {"content": text}}

    elif fmt == "feishu":
        payload = {"msg_type": "text", "content": {"text": text}}

    elif fmt == "custom":
        # 使用模板渲染，直接字符串替换避免 str.format 的花括号冲突
        items_json = json.dumps(items, ensure_ascii=False)
        rendered = WEBHOOK_TEMPLATE \
            .replace("{text}", text) \
            .replace("{count}", str(count)) \
            .replace("{items_json}", items_json)
        try:
            payload = json.loads(rendered)
        except json.JSONDecodeError:
            # 非合法 JSON，就当纯文本发
            payload = {"text": rendered}

    else:  # generic
        payload = {
            "event": "reminder",
            "text": text,
            "count": count,
            "items": [
                {
                    "title": it["title"],
                    "priority": it.get("priority"),
                    "start_at": it["start_at"],
                    "end_at": it.get("end_at"),
                }
                for it in items
            ],
        }

    return payload, json.dumps(payload, ensure_ascii=False)


# ---------- 推送 ----------

def _get_headers():
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_HEADERS:
        try:
            extra = json.loads(WEBHOOK_HEADERS)
            headers.update(extra)
        except json.JSONDecodeError as e:
            log.warning("WEBHOOK_HEADERS JSON 解析失败: %s", e)
    return headers


def push(text, items, event_type="reminder"):
    """
    推送消息到 webhook。
    返回 dict: {success, status_code, error, retry_count, duration_ms, log_id}
    """
    payload, payload_str = _build_payload(text, items)
    headers = _get_headers()

    # 未配置 URL：只打印，记录日志
    if not WEBHOOK_URL:
        print("\n" + "=" * 50)
        print(f"[webhook 未配置] {event_type}")
        print(text)
        print("=" * 50 + "\n")
        log_id = db.insert_webhook_log(
            event_type=event_type, url="(not configured)",
            payload=payload_str, status_code=None, response_body=None,
            success=0, error="webhook url not configured",
            retry_count=0, duration_ms=0,
        )
        return {"success": False, "status_code": None,
                "error": "not configured", "retry_count": 0,
                "duration_ms": 0, "log_id": log_id, "payload": payload}

    success = False
    status_code = None
    response_body = None
    error_msg = None
    retry_count = 0
    start_ts = time.time()

    for attempt in range(WEBHOOK_RETRY + 1):
        retry_count = attempt
        try:
            r = requests.post(
                WEBHOOK_URL, headers=headers, json=payload, timeout=WEBHOOK_TIMEOUT,
            )
            status_code = r.status_code
            response_body = r.text[:500]

            # 判定成功：HTTP 2xx
            if 200 <= r.status_code < 300:
                # 进一步检查已知平台的业务码
                if WEBHOOK_FORMAT == "wecom":
                    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    if body.get("errcode") not in (0, None):
                        error_msg = f"wecom errcode={body.get('errcode')}, msg={body.get('errmsg')}"
                        raise ValueError(error_msg)
                elif WEBHOOK_FORMAT == "feishu":
                    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    code = body.get("code", body.get("StatusCode", 0))
                    if code not in (0, None):
                        error_msg = f"feishu code={code}, msg={body.get('msg') or body.get('StatusMessage')}"
                        raise ValueError(error_msg)

                success = True
                break

            error_msg = f"HTTP {r.status_code}: {response_body[:200]}"

        except requests.exceptions.Timeout:
            error_msg = f"timeout after {WEBHOOK_TIMEOUT}s"
        except requests.exceptions.ConnectionError as e:
            error_msg = f"connection error: {e}"
        except Exception as e:
            error_msg = error_msg or str(e)

        # 重试退避
        if attempt < WEBHOOK_RETRY:
            wait = 2 ** attempt
            log.warning("推送失败 (attempt %d/%d): %s, %ds 后重试",
                        attempt + 1, WEBHOOK_RETRY + 1, error_msg, wait)
            time.sleep(wait)

    duration_ms = int((time.time() - start_ts) * 1000)

    log_id = db.insert_webhook_log(
        event_type=event_type, url=WEBHOOK_URL,
        payload=payload_str, status_code=status_code,
        response_body=response_body,
        success=1 if success else 0, error=error_msg,
        retry_count=retry_count, duration_ms=duration_ms,
    )

    if success:
        log.info("webhook 推送成功 (attempt %d, %dms)", retry_count + 1, duration_ms)
    else:
        log.error("webhook 推送最终失败: %s", error_msg)

    return {
        "success": success,
        "status_code": status_code,
        "error": error_msg,
        "retry_count": retry_count,
        "duration_ms": duration_ms,
        "log_id": log_id,
    }


def scan_and_remind():
    """
    扫描需要提醒的排期并推送。
    返回本次推送的条数。
    """
    pending = db.get_pending_reminders(lead_minutes=REMIND_LEAD_MINUTES)
    if not pending:
        return 0

    text = _format_text(pending)
    result = push(text, pending, event_type="reminder")

    # 推送成功（或未配置 URL — 开发模式下也标记已发，避免反复打印）
    if result["success"] or not WEBHOOK_URL:
        for item in pending:
            db.mark_reminder_sent(item["id"])

    return len(pending)
