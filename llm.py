"""OpenAI-compatible structured intent parsing for agenda creation."""

from __future__ import annotations

import json
import os
from datetime import date, datetime

import requests
from jsonschema import Draft202012Validator


INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": ["string", "null"], "maxLength": 500},
        "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "start_time": {"type": ["string", "null"], "pattern": r"^\d{2}:\d{2}$"},
        "duration_min": {"type": ["integer", "null"], "minimum": 1, "maximum": 1440},
        "reminder_requested": {"type": "boolean"},
        "reminder_minutes": {"type": ["integer", "null"], "minimum": 0, "maximum": 10080},
        "timezone": {"type": ["string", "null"], "maxLength": 64},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"], "maxLength": 500},
    },
    "required": ["title", "date", "start_time", "duration_min", "reminder_requested", "reminder_minutes",
                 "timezone", "needs_clarification", "clarification_question"],
    "additionalProperties": False,
}


class IntentParseError(Exception):
    """An LLM configuration, transport, or structured-output error."""


LLM_PROVIDER_DEFAULTS = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
}


def intent_parser_from_env(*, post=requests.post):
    """Build a parser from deployment config, or return None when disabled."""
    provider = os.getenv("SCHEDULE_LLM_PROVIDER", "").strip().lower()
    base_url = os.getenv("SCHEDULE_LLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("SCHEDULE_LLM_MODEL", "").strip()
    api_key = os.getenv("SCHEDULE_LLM_API_KEY", "").strip()
    if provider and provider not in LLM_PROVIDER_DEFAULTS and provider != "custom":
        raise IntentParseError("不支持的 LLM provider")
    preset = LLM_PROVIDER_DEFAULTS.get(provider)
    if preset:
        base_url = base_url or preset["base_url"]
        model = model or preset["model"]
    elif provider == "custom" and not base_url:
        raise IntentParseError("custom provider 需要 SCHEDULE_LLM_BASE_URL")
    configured = (base_url, model, api_key)
    if not any(configured):
        return None
    if not all(configured):
        raise IntentParseError("LLM 配置不完整")
    try:
        timeout = float(os.getenv("SCHEDULE_LLM_TIMEOUT", "20"))
    except ValueError as exc:
        raise IntentParseError("LLM 超时配置无效") from exc
    if not 0 < timeout <= 120:
        raise IntentParseError("LLM 超时配置无效")
    return OpenAICompatibleIntentParser(base_url, model, api_key, provider=provider or "custom",
                                       timeout=timeout, post=post)


class OpenAICompatibleIntentParser:
    def __init__(self, base_url, model, api_key, *, provider="custom", timeout=20, post=requests.post):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.provider = provider
        self.timeout = timeout
        self.post = post

    def parse(self, text: str, *, timezone: str, today: date) -> dict:
        system = (
            "Extract one calendar intent from the user's text. Return only JSON matching the requested fields. "
            "Always include every field: title, date, start_time, duration_min, reminder_requested, "
            "reminder_minutes, timezone, needs_clarification, clarification_question. "
            "Use the exact field name reminder_minutes, never reminder_min. "
            "Use the supplied IANA timezone. Resolve relative dates against today in that timezone. "
            "Use null for information not stated. duration_min is null when omitted. "
            "Set needs_clarification and ask a concise question when the request has multiple plausible meanings "
            "or lacks a title; otherwise set clarification_question to null. Never create SQL or choose a schedule slot."
        )
        user = json.dumps({"text": text, "timezone": timezone, "today": today.isoformat()}, ensure_ascii=False)
        try:
            response = self.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "temperature": 0,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            intent = json.loads(content)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise IntentParseError("LLM 请求失败或响应格式无效") from exc
        if isinstance(intent, dict):
            # Normalize common provider omissions/aliases before strict validation.
            if "reminder_minutes" not in intent and "reminder_min" in intent:
                intent["reminder_minutes"] = intent.pop("reminder_min")
            intent.setdefault("timezone", timezone)
            if not isinstance(intent.get("reminder_requested"), bool):
                intent["reminder_requested"] = intent.get("reminder_minutes") is not None
            intent.setdefault("needs_clarification", False)
            intent.setdefault("clarification_question", None)
        errors = list(Draft202012Validator(INTENT_SCHEMA).iter_errors(intent))
        if errors:
            raise IntentParseError("LLM 输出不符合日程意图 schema")
        if intent["needs_clarification"]:
            if not intent["clarification_question"]:
                raise IntentParseError("LLM 未提供澄清问题")
            return intent
        if not intent["title"] or not intent["date"]:
            raise IntentParseError("LLM 输出缺少标题或日期")
        try:
            date.fromisoformat(intent["date"])
            if intent["start_time"] is not None:
                datetime.strptime(intent["start_time"], "%H:%M")
        except ValueError as exc:
            raise IntentParseError("LLM 输出的日期或时间无效") from exc
        return intent
