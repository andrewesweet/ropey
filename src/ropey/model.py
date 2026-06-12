"""Published vocabulary of the tool boundary.

Every type here is part of the language the agent sees (see CONTEXT.md).
No rope type and no MCP type appears in this module; it depends on nothing
else in the package.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Position:
    """A point in a file: 0-based line, character in UTF-16 code units (LSP)."""

    line: int
    character: int


@dataclass(frozen=True)
class Range:
    """A span of source delimited by a start and end Position (LSP)."""

    start: Position
    end: Position


class ChangeKind(str, Enum):
    """What happens to one affected resource in the Blast Radius."""

    MODIFIED = "modified"
    CREATED = "created"
    MOVED = "moved"
    DELETED = "deleted"


@dataclass(frozen=True)
class BlastRadiusEntry:
    """One affected resource: path, Change Kind, short description, old path for moves."""

    path: str
    change_kind: ChangeKind
    description: str
    old_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "path": self.path,
            "change_kind": self.change_kind.value,
            "description": self.description,
        }
        if self.old_path is not None:
            entry["old_path"] = self.old_path
        return entry


@dataclass(frozen=True)
class UncertainOccurrence:
    """A candidate occurrence rope could not prove refers to the Target.

    Never silently applied, never silently dropped: surfaced as a flagged
    Location for the agent to adjudicate.
    """

    path: str
    position: Position
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.position.line,
            "character": self.position.character,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class RefactoringReport:
    """The result of a Refactoring: identical detail on Dry Run and Live Run."""

    applied: bool
    blast_radius: tuple[BlastRadiusEntry, ...]
    uncertain_occurrences: tuple[UncertainOccurrence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "applied" if self.applied else "dry_run",
            "blast_radius": [entry.to_dict() for entry in self.blast_radius],
            "uncertain_occurrences": [
                occurrence.to_dict() for occurrence in self.uncertain_occurrences
            ],
        }


class StructuredFailure(Exception):
    """A Refactoring that cannot proceed: states the failed precondition.

    ``kind`` is a stable machine-readable code, ``reason`` a sentence in the
    glossary vocabulary. ``detail`` may carry the engine's own message as
    supplementary context but is never the primary reason.
    """

    def __init__(self, kind: str, reason: str, detail: str | None = None):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        failure: dict[str, Any] = {"kind": self.kind, "reason": self.reason}
        if self.detail:
            failure["detail"] = self.detail
        return {"status": "failure", "failure": failure}


class FailureKind:
    """Stable machine-readable codes for Structured Failures."""

    ROOT_REQUIRED = "root-required"
    ROOT_NOT_FOUND = "root-not-found"
    FILE_NOT_FOUND = "file-not-found"
    FILE_OUT_OF_SCOPE = "file-out-of-scope"
    POSITION_OUT_OF_RANGE = "position-out-of-range"
    EXPECTED_SYMBOL_MISMATCH = "expected-symbol-mismatch"
    TARGET_NOT_REFACTORABLE = "target-not-refactorable"
    INVALID_SELECTION = "invalid-selection"
    UNPARSABLE_FILE = "unparsable-file"
    INVALID_ARGUMENT = "invalid-argument"
    INTERNAL_ERROR = "internal-error"
