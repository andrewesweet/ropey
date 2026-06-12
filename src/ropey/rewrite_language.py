"""Rewrite Language: validation of the Pattern-addressed input language.

The input-side seam of the Rewrite sibling (ADR 0005). Pattern, Goal, and
Wildcard cross the boundary verbatim — ropey is a Conformist to rope's
published Restructure language — so this module checks the agent's
templates against the published preconditions before any matching starts:
a malformed Pattern or Goal is a Structured Failure stating the failed
precondition, never a half-applied rewrite.

Wildcard extraction delegates to rope's own template parser so that what
ropey validates is exactly what rope will match.
"""

from __future__ import annotations

import ast
import textwrap

from rope.refactor.similarfinder import CodeTemplate

from .model import FailureKind, StructuredFailure


def validate_templates(pattern: str, goal: str) -> frozenset[str]:
    """Check the published Pattern/Goal preconditions; return the Wildcards.

    Preconditions (PRD 0002 "Failure modes"): the Pattern parses as Python
    once its Wildcards stand in for names, it contains at least one
    Wildcard, every Wildcard names a valid identifier, the Goal parses the
    same way, and the Goal references only Pattern Wildcards.
    """
    pattern_wildcards = _wildcard_names(
        pattern, FailureKind.INVALID_PATTERN, "Pattern"
    )
    if not pattern_wildcards:
        raise StructuredFailure(
            FailureKind.INVALID_PATTERN,
            "The Pattern contains no ${wildcard} placeholders. A Rewrite "
            "matches a structural shape, so the Pattern needs at least one "
            "Wildcard (e.g. ${obj}.get_attribute(${key})).",
        )
    goal_wildcards = _wildcard_names(goal, FailureKind.INVALID_GOAL, "Goal")
    unknown = goal_wildcards - pattern_wildcards
    if unknown:
        raise StructuredFailure(
            FailureKind.INVALID_GOAL,
            f"The Goal references {_wildcard_list(unknown)} but the Pattern "
            f"binds only {_wildcard_list(pattern_wildcards)}. A Goal can only "
            "reuse Wildcards the Pattern matched.",
        )
    _ensure_pattern_parses(pattern, pattern_wildcards)
    _ensure_goal_parses(goal, goal_wildcards)
    return frozenset(pattern_wildcards)


def _wildcard_names(template: str, kind: str, label: str) -> set[str]:
    names = set(CodeTemplate(template).get_names())
    malformed = {name for name in names if not name.isidentifier()}
    if malformed:
        raise StructuredFailure(
            kind,
            f"The {label} Wildcard {_wildcard_list(malformed)} is not a "
            "valid identifier; name Wildcards like ${obj} or ${key_1}.",
        )
    return names


def _wildcard_list(names: set[str]) -> str:
    return ", ".join(f"${{{name}}}" for name in sorted(names))


def _substitute_names(template: str, wildcards: set[str]) -> str:
    """Each ``${name}`` becomes the bare identifier ``name`` (parse stand-in)."""
    return CodeTemplate(template).substitute({name: name for name in wildcards})


def _ensure_pattern_parses(pattern: str, wildcards: set[str]) -> None:
    try:
        ast.parse(_substitute_names(pattern, wildcards))
    except SyntaxError as error:
        raise StructuredFailure(
            FailureKind.INVALID_PATTERN,
            "The Pattern does not parse as Python once its Wildcards stand "
            "in for names. Write the Pattern as a Python expression or "
            "statement block with ${wildcard} placeholders.",
            detail=str(error),
        ) from error


def _ensure_goal_parses(goal: str, wildcards: set[str]) -> None:
    substituted = _substitute_names(goal, wildcards)
    try:
        ast.parse(substituted)
        return
    except SyntaxError as error:
        failure = error
    # return / yield / await fragments are valid Goals despite not parsing
    # at module level; retry in a function body before refusing.
    wrapped = "async def _goal():\n" + textwrap.indent(substituted, "    ")
    try:
        ast.parse(wrapped)
    except SyntaxError:
        raise StructuredFailure(
            FailureKind.INVALID_GOAL,
            "The Goal does not parse as Python once its Wildcards stand in "
            "for names. Write the Goal as the replacement expression or "
            "statement block, reusing the Pattern's ${wildcard} names.",
            detail=str(failure),
        ) from failure
