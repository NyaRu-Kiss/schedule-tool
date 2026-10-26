"""Stateless Streamable HTTP transport; tools are forwarded to AgendaAgent."""

import hmac
import json
import os

from flask import Flask, jsonify, request

from mcp import AgendaMCP, _rpc_error
from mcp_runtime import build_server


HTTP_VERSIONS = tuple(v for v in AgendaMCP.PROTOCOL_VERSIONS if v >= "2025-03-26")


def create_http_app(server_factory=build_server, *, token=None, allowed_origins=None):
    token = token if token is not None else os.environ.get("SCHEDULE_MCP_HTTP_TOKEN", "")
    if not token or not token.strip():
        raise ValueError("SCHEDULE_MCP_HTTP_TOKEN must be configured")
    if allowed_origins is None:
        allowed_origins = os.environ.get("SCHEDULE_MCP_ALLOWED_ORIGINS", "").split(",")
    origins = {origin.strip() for origin in allowed_origins if origin.strip()}
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

    @app.route("/mcp", methods=["POST", "GET", "DELETE"], provide_automatic_options=False)
    def endpoint():
        origin = request.headers.get("Origin")
        if origin is not None and origin not in origins:
            return jsonify(error="Origin is not allowed"), 403
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return jsonify(error="Unauthorized"), 401, {"WWW-Authenticate": "Bearer"}
        if request.method != "POST":
            return "", 405, {"Allow": "POST"}
        if (request.accept_mimetypes["application/json"] <= 0
                or request.accept_mimetypes["text/event-stream"] <= 0):
            return jsonify(error="Accept must include application/json and text/event-stream"), 406
        if request.mimetype != "application/json":
            return jsonify(error="Content-Type must be application/json"), 415
        version = request.headers.get("MCP-Protocol-Version", "2025-03-26")
        if version not in HTTP_VERSIONS:
            return jsonify(error="Unsupported MCP protocol version"), 400
        try:
            message = json.loads(request.get_data(), parse_constant=_reject_constant)
        except (ValueError, UnicodeDecodeError):
            return jsonify(_rpc_error(None, -32700, "JSON 解析失败")), 400
        if not isinstance(message, dict):
            return jsonify(_rpc_error(None, -32600, "无效请求")), 400
        # Clients may submit responses to server requests; this server makes none.
        if (message.get("jsonrpc") == "2.0" and "method" not in message
                and type(message.get("id")) in (str, int)
                and (("result" in message) != ("error" in message))):
            return "", 202
        server = server_factory()
        # Request-local connector prevents clients from sharing negotiated versions.
        server.protocol_version = version
        if message.get("method") == "initialize":
            params = message.get("params")
            if isinstance(params, dict) and isinstance(params.get("protocolVersion"), str):
                if params["protocolVersion"] not in HTTP_VERSIONS:
                    message = {**message, "params": {**params, "protocolVersion": HTTP_VERSIONS[0]}}
        response = server.handle_rpc(message)
        if response is None:
            return "", 202
        return jsonify(response), 400 if response.get("error", {}).get("code") == -32600 else 200

    return app


def _reject_constant(value):
    raise ValueError("Invalid JSON constant")


def main():
    create_http_app().run(
        host=os.environ.get("SCHEDULE_MCP_HTTP_HOST", "127.0.0.1"),
        port=int(os.environ.get("SCHEDULE_MCP_HTTP_PORT", "7801")),
        debug=False, use_reloader=False,
    )


if __name__ == "__main__":
    main()
