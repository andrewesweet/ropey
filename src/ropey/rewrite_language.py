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
from typing import Any, cast

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


_SYMBOL_KEYS = ("name", "type", "object", "instance")
_FLAG_KEYS = ("exact", "unsure")
_CONSTRAINT_KEYS = _SYMBOL_KEYS + _FLAG_KEYS

ConstraintArgs = dict[str, dict[str, str | bool]]


def validate_constraints(
    constraints: dict[str, dict[str, object]] | None,
    wildcards: frozenset[str],
) -> ConstraintArgs:
    """Check the Match Constraints; return them as per-Wildcard matcher args.

    Published keys: ``name``/``type``/``object``/``instance`` narrow by a
    symbol's dotted path (at most one per Wildcard — they are alternative
    checks, and silently ranking them would hide which one applied);
    ``exact`` narrows to the Wildcard's literal name; ``unsure`` widens to
    sites where the symbol check cannot be established.
    """
    args: ConstraintArgs = {}
    for wildcard, spec in (constraints or {}).items():
        if wildcard not in wildcards:
            raise StructuredFailure(
                FailureKind.INVALID_MATCH_CONSTRAINT,
                f"The Match Constraint on ${{{wildcard}}} names no Pattern "
                f"Wildcard; the Pattern binds {_wildcard_list(set(wildcards))}.",
            )
        args[wildcard] = _validated_spec(wildcard, spec)
    return args


def _validated_spec(wildcard: str, spec: object) -> dict[str, str | bool]:
    if not isinstance(spec, dict):
        raise StructuredFailure(
            FailureKind.INVALID_MATCH_CONSTRAINT,
            f"The Match Constraint on ${{{wildcard}}} is not an object; pass "
            'e.g. {"type": "myapp.models.User"} or {"exact": true}.',
        )
    validated: dict[str, str | bool] = {}
    for key, value in cast(dict[str, Any], spec).items():
        if key not in _CONSTRAINT_KEYS:
            raise StructuredFailure(
                FailureKind.INVALID_MATCH_CONSTRAINT,
                f"Unknown Match Constraint key {key!r} on ${{{wildcard}}}; "
                f"the keys are {', '.join(_CONSTRAINT_KEYS)}.",
            )
        if key in _SYMBOL_KEYS:
            if not isinstance(value, str) or not value:
                raise StructuredFailure(
                    FailureKind.INVALID_MATCH_CONSTRAINT,
                    f"The {key} Match Constraint on ${{{wildcard}}} needs a "
                    "symbol's dotted path (e.g. myapp.models.User); got "
                    f"{value!r}.",
                )
            validated[key] = value
        else:
            if not isinstance(value, bool):
                raise StructuredFailure(
                    FailureKind.INVALID_MATCH_CONSTRAINT,
                    f"The {key} Match Constraint on ${{{wildcard}}} is a "
                    f"flag; pass true or false, got {value!r}.",
                )
            if value:
                validated[key] = True
    symbol_keys = [key for key in _SYMBOL_KEYS if key in validated]
    if len(symbol_keys) > 1:
        raise StructuredFailure(
            FailureKind.INVALID_MATCH_CONSTRAINT,
            f"${{{wildcard}}} carries {' and '.join(symbol_keys)} together; "
            "name, type, object and instance are alternative checks — "
            "choose one per Wildcard.",
        )
    return validated


def narrowing_args(args: ConstraintArgs) -> ConstraintArgs:
    """The args with every ``unsure`` widening removed: the certainty baseline."""
    return {
        wildcard: {key: value for key, value in spec.items() if key != "unsure"}
        for wildcard, spec in args.items()
    }


def widening_args(args: ConstraintArgs) -> ConstraintArgs:
    """The args with ``unsure`` set wherever a symbol check could fail to be
    established: the full candidate set, certain and unsure alike."""
    widened: ConstraintArgs = {}
    for wildcard, spec in args.items():
        if any(key in spec for key in _SYMBOL_KEYS):
            widened[wildcard] = {**spec, "unsure": True}
        else:
            widened[wildcard] = dict(spec)
    return widened


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
