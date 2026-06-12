"""Syntax Guard: no Rewrite ever applies unparsable Python.

The Rewrite is the one tool that can mechanically emit broken code —
template substitution makes no syntax guarantee (ADR 0005). Sited at the
Change Set -> Blast Radius seam and run whenever the Change Set is
computed, in both modes: nothing forces a Dry Run first, so a cold Live
Run with a syntax-breaking Goal refuses identically, with nothing written.
"""

from __future__ import annotations

import ast

from rope.base.change import Change, ChangeContents, ChangeSet

from .model import FailureKind, StructuredFailure


def ensure_parsable(change_set: Change) -> None:
    """Parse-check every module the Change Set would modify."""
    for change in _content_changes(change_set):
        try:
            ast.parse(change.new_contents)
        except SyntaxError as error:
            raise _broken_syntax(change.resource.path, error) from error


def _content_changes(change: Change):
    if isinstance(change, ChangeSet):
        for child in change.changes:
            yield from _content_changes(child)
    elif isinstance(change, ChangeContents):
        yield change


def _broken_syntax(path: str, error: SyntaxError) -> StructuredFailure:
    line = (error.lineno or 1) - 1
    character = (error.offset or 1) - 1
    return StructuredFailure(
        FailureKind.REWRITE_WOULD_BREAK_SYNTAX,
        f"The Rewrite would produce unparsable Python in {path} (line "
        f"{line}, character {character}, 0-based, of the rewritten text); "
        "nothing was applied. The Goal does not fit every context the "
        "Pattern matched — adjust the Goal, or tighten the Pattern or "
        "Match Constraints to exclude that site.",
        detail=str(error),
    )
