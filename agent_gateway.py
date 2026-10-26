"""HTTP transport used by the local Agent to call the trusted backend."""

from __future__ import annotations

import os

import requests

from agent import error_response


def backend_call_from_env(timeout: float = 10):
    url = (os.getenv("SCHEDULE_BACKEND_URL", "http://127.0.0.1:7800").rstrip("/")
           + "/api/internal/sql/execute")

    def backend_call(payload):
        try:
            headers = {}
            token = os.getenv("SCHEDULE_INTERNAL_SERVICE_TOKEN", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("success"), bool):
                raise ValueError("invalid backend response")
            if body["success"]:
                response.raise_for_status()
            else:
                error = body.get("error")
                if (type(body.get("retryable")) is not bool
                        or not isinstance(error, dict)
                        or set(error) != {"code", "message"}
                        or not all(isinstance(error[key], str) for key in error)):
                    raise ValueError("invalid backend error response")
        except (requests.RequestException, ValueError):
            return error_response("INTERNAL_ERROR", "后端不可用或返回了无效响应", retryable=False)
        return body

    return backend_call
