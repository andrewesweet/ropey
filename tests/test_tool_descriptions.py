"""Mechanical enforcement of the tool-description standard (issue #13).

See docs/tool-description-standard.md for the derivation; these tests pin
the checks that don't need judgement, so a regression fails CI.
"""

from __future__ import annotations

import re

import anyio
import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as _connect,
)

from ropey.server import create_server

POINT_TOOLS = {"rename", "inline", "change_signature", "move"}
SELECTION_TOOLS = {"extract_method", "extract_variable"}
FILE_ONLY_TOOLS = {"module_to_package", "organize_imports"}

OVER_STRONG_MODALS = ["CRITICAL", "MUST", "ALWAYS", "NEVER", "IMPORTANT"]
ENGINE_INTERNALS = [r"\brope\b", r"\boffsets?\b", r"\bChangeSet\b"]


@pytest.fixture(scope="module")
def descriptions() -> dict[str, str]:
    async def go():
        server = create_server()
        async with _connect(server._mcp_server) as client:
            listing = await client.list_tools()
            return {tool.name: tool.description or "" for tool in listing.tools}

    return anyio.run(go)


def test_the_whole_catalogue_is_registered(descriptions):
    assert set(descriptions) == POINT_TOOLS | SELECTION_TOOLS | FILE_ONLY_TOOLS


def test_no_over_strong_modal_phrasing(descriptions):
    for name, text in descriptions.items():
        for modal in OVER_STRONG_MODALS:
            assert modal not in text, f"{name}: over-strong {modal!r}"


def test_no_engine_internals_cross_the_boundary(descriptions):
    for name, text in descriptions.items():
        for pattern in ENGINE_INTERNALS:
            assert not re.search(pattern, text), f"{name}: internal {pattern!r}"


def test_every_tool_documents_the_transaction_model(descriptions):
    for name, text in descriptions.items():
        assert "Dry Run" in text, f"{name}: Dry Run default not documented"
        assert "apply=true" in text, f"{name}: apply flag not documented"


def test_every_tool_routes_neighbouring_work(descriptions):
    for name, text in descriptions.items():
        assert "LSP" in text or "black/ruff" in text, f"{name}: no routing"


def test_coordinate_tools_state_the_convention(descriptions):
    for name in POINT_TOOLS | SELECTION_TOOLS:
        text = descriptions[name]
        assert "0-based" in text, f"{name}: 0-based not stated"
        assert "UTF-16" in text, f"{name}: UTF-16 units not stated"


def test_point_tools_document_the_expected_symbol_guard(descriptions):
    for name in {"rename", "inline"}:
        assert "expected_symbol" in descriptions[name], (
            f"{name}: expected_symbol guidance missing"
        )
