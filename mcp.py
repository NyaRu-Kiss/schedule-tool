"""WorkBuddy 日程 MCP 连接器。

该模块只做协议适配和 Agent 调用，不包含数据库客户端、数据访问或业务决策。
默认通过 HTTP 将 Agent 生成的请求交给后端；测试和宿主程序也可以注入 Agent。
"""

from __future__ import annotations

import json
import sys
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator

from agent import AgendaAgent, error_response


class AgendaMCP:
    """Expose exactly the three WorkBuddy agenda tools."""

    TOOL_NAMES = ("create_schedule", "poll_reminders", "ack_reminder")
    PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
    TOOLS = (
        {"name": "create_schedule", "description": "根据自然语言创建日程",
         "inputSchema": {"type": "object", "properties": {
             "text": {"type": "string", "minLength": 1, "description": "日程描述"},
             "request_id": {"type": "string", "minLength": 1, "maxLength": 64},
             "timezone": {"type": "string", "description": "IANA 时区，如 Asia/Shanghai"}},
             "required": ["text", "request_id"], "additionalProperties": False}},
        {"name": "poll_reminders", "description": "查询到期且未发送的提醒",
         "inputSchema": {"type": "object", "properties": {
             "request_id": {"type": "string", "minLength": 1, "maxLength": 64},
             "now": {"type": "string", "description": "带时区的 ISO 8601 时间"},
             "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100}},
             "required": ["request_id"], "additionalProperties": False}},
        {"name": "ack_reminder", "description": "确认提醒发送结果",
         "inputSchema": {"type": "object", "properties": {
             "request_id": {"type": "string", "minLength": 1, "maxLength": 64},
             "scheduled_task_id": {"type": "integer", "minimum": 1},
             "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 128},
             "status": {"type": "string", "enum": ["SENT", "FAILED"], "default": "SENT"},
             "error": {"type": "string", "maxLength": 1000},
             "now": {"type": "string", "description": "带时区的 ISO 8601 时间"}},
             "required": ["request_id", "scheduled_task_id", "idempotency_key"],
             "additionalProperties": False}},
    )

    def __init__(self, agent: AgendaAgent):
        self.agent = agent

    def create_schedule(self, arguments: dict[str, Any]) -> dict:
        return self.agent.create_schedule(arguments.get("text"), arguments.get("request_id"),
                                          timezone=arguments.get("timezone"))

    def poll_reminders(self, arguments: dict[str, Any]) -> dict:
        return self.agent.poll_reminders(arguments.get("request_id"), now=arguments.get("now"),
                                         limit=arguments.get("limit", 100))

    def ack_reminder(self, arguments: dict[str, Any]) -> dict:
        return self.agent.ack_reminder(
            arguments.get("request_id"), arguments.get("scheduled_task_id"),
            arguments.get("idempotency_key"), status=arguments.get("status", "SENT"),
            error=arguments.get("error"), now=arguments.get("now"),
        )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict:
        if name not in self.TOOL_NAMES:
            return error_response("INVALID_ARGUMENT", f"未知 MCP 工具: {name}", retryable=False)
        schema = next(tool["inputSchema"] for tool in self.TOOLS if tool["name"] == name)
        errors = list(Draft202012Validator(schema).iter_errors(arguments))
        if errors:
            return error_response("INVALID_ARGUMENT", errors[0].message, retryable=False)
        if "timezone" in arguments:
            try:
                ZoneInfo(arguments["timezone"])
            except (ZoneInfoNotFoundError, ValueError):
                return error_response("INVALID_ARGUMENT", "timezone 必须是有效的 IANA 时区", retryable=False)
        try:
            result = getattr(self, name)(arguments)
            if not isinstance(result, dict):
                raise ValueError("invalid agent response")
            json.dumps(result, allow_nan=False)
            return result
        except Exception:
            return error_response("INTERNAL_ERROR", "工具执行失败", retryable=False)

    def handle_rpc(self, request: Any) -> dict | None:
        """Handle MCP-compatible initialize, tools/list and tools/call messages."""
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return _rpc_error(request.get("id") if isinstance(request, dict) and type(request.get("id")) in (str, int) else None,
                              -32600, "无效请求")
        request_id = request.get("id")
        if "id" in request and type(request_id) not in (str, int):
            return _rpc_error(None, -32600, "无效请求 ID")
        method = request.get("method")
        if "id" not in request:
            return None
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _rpc_error(request_id, -32602, "参数必须是对象")
        if method == "initialize":
            version = params.get("protocolVersion")
            if not isinstance(version, str):
                return _rpc_error(request_id, -32602, "缺少 protocolVersion")
            negotiated = version if version in self.PROTOCOL_VERSIONS else self.PROTOCOL_VERSIONS[0]
            self.protocol_version = negotiated
            result = {"protocolVersion": negotiated, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "agenda-mcp", "version": "1.0.0"}}
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.TOOLS}}
        if method == "tools/call":
            if not isinstance(params.get("name"), str):
                return _rpc_error(request_id, -32602, "缺少工具名称")
            result = self.call_tool(params.get("name"), params.get("arguments"))
            tool_result = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                           "isError": result.get("success") is False}
            if getattr(self, "protocol_version", "2024-11-05") >= "2025-06-18":
                tool_result["structuredContent"] = result
            return {"jsonrpc": "2.0", "id": request_id, "result": tool_result}
        return _rpc_error(request_id, -32601, "方法不存在")


def _rpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve_stdio(server: AgendaMCP, *, input_stream=None, output_stream=None) -> None:
    """Run one JSON request per line until stdin closes."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = _rpc_error(None, -32700, "JSON 解析失败")
        else:
            response = server.handle_rpc(request)
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()


if __name__ == "__main__":
    from mcp_runtime import main

    main()
