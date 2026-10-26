"""Composition root for the local Agent and stdio MCP transport."""

from agent import AgendaAgent
from agent_gateway import backend_call_from_env
from mcp import AgendaMCP, serve_stdio


def build_server(backend_call=None):
    return AgendaMCP(AgendaAgent(backend_call or backend_call_from_env()))


def main():
    serve_stdio(build_server())


if __name__ == "__main__":
    main()
