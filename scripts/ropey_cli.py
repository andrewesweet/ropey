"""Drive ropey's MCP tools from a shell — the dogfooding harness.

Usage: uv run python scripts/ropey_cli.py <tool> '<json-arguments>'

Talks to the real server through an in-memory MCP client session, so a
call here exercises exactly what a host would.
"""

from __future__ import annotations

import json
import sys

import anyio
from mcp.shared.memory import (
    create_connected_server_and_client_session as connect,
)

from ropey.server import create_server


async def call(tool: str, arguments: dict) -> dict:
    server = create_server()
    async with connect(server._mcp_server) as client:
        result = await client.call_tool(tool, arguments)
        if isinstance(result.structuredContent, dict):
            return result.structuredContent
        return json.loads(result.content[0].text)


def main() -> None:
    tool = sys.argv[1]
    arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(anyio.run(call, tool, arguments), indent=2))


if __name__ == "__main__":
    main()
