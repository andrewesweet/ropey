"""Test harness: fixture repositories and the tool boundary.

Tests speak only the published vocabulary: they call MCP tools through a
real client session and assert on files, Blast Radius, Uncertain
Occurrences, and Structured Failures — never rope internals or wiring.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as _connect,
)

from ropey.server import create_server


@pytest.fixture
def make_repo(tmp_path):
    """Create a git-rooted fixture repository from a {path: content} mapping."""

    def _make(files: dict[str, str], *, git: bool = True, name: str = "repo") -> Path:
        repo = tmp_path / name
        repo.mkdir(parents=True, exist_ok=True)
        for relative, content in files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        if git:
            subprocess.run(
                ["git", "init", "-q"], cwd=repo, check=True, capture_output=True
            )
        return repo

    return _make


@pytest.fixture
def server():
    """A freshly composed server; state (the Project cache) lives for the test."""
    return create_server()


@pytest.fixture
def call_tool(server):
    """Call one MCP tool through a real in-memory client session."""

    def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async def go():
            async with _connect(server._mcp_server) as client:
                result = await client.call_tool(name, arguments)
                if isinstance(result.structuredContent, dict):
                    payload = result.structuredContent
                    if "status" not in payload and "result" in payload:
                        payload = payload["result"]
                    return payload
                first = result.content[0]
                text = getattr(first, "text", None)
                assert isinstance(text, str), f"unexpected content: {first!r}"
                return json.loads(text)

        return anyio.run(go)

    return _call


def blast_paths(report: dict[str, Any]) -> set[str]:
    return {entry["path"] for entry in report["blast_radius"]}


def entry_for(report: dict[str, Any], path: str) -> dict[str, Any]:
    matches = [e for e in report["blast_radius"] if e["path"] == path]
    assert matches, f"{path} not in blast radius: {report['blast_radius']}"
    return matches[0]
