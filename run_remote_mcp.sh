#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
[ -f .env ] && . ./.env
set +a
: "${SCHEDULE_MCP_HTTP_TOKEN:?Set SCHEDULE_MCP_HTTP_TOKEN in .env}"
: "${SCHEDULE_INTERNAL_SERVICE_TOKEN:?Set SCHEDULE_INTERNAL_SERVICE_TOKEN in .env}"

python3 -c 'from app import app; app.run(host="127.0.0.1", port=7800, debug=False, use_reloader=False)' >backend.log 2>&1 &
BACKEND_PID=$!
python3 mcp_http.py &
MCP_PID=$!
cleanup() {
  kill "$MCP_PID" "$BACKEND_PID" 2>/dev/null || true
  wait "$MCP_PID" "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
sleep 1
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo 'backend failed to start' >&2
  exit 1
fi
cloudflared tunnel --config "$HOME/.cloudflared/config.yml" run a5d9a5e9-502e-4ee7-8c41-b7654f5c9755
