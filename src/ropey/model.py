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

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass(frozen=True)
class Range:
    """A span of source delimited by a start and end Position (LSP)."""

    start: Position
    end: Position

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


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


class MatchCertainty(str, Enum):
    """A Match Site's footing: a claim about Match Constraint satisfaction only.

    Never an equivalence claim — nothing in a Rewrite is tool-proven
    (ADR 0005), so "proven" is deliberately absent from this vocabulary.
    """

    MATCHED = "matched"
    UNSURE = "unsure"


@dataclass(frozen=True)
class MatchSite:
    """A Location where a Rewrite's Pattern fired, in pre-apply coordinates.

    On a Dry Run the Range is a live target for the LSP; after a Live Run
    it is an audit record of the pre-apply text (``git diff`` verifies the
    new text). ``included`` states whether the site is part of the rewrite:
    an unsure site is included only when its Wildcard sets the ``unsure``
    Match Constraint.
    """

    path: str
    range: Range
    snippet: str
    certainty: MatchCertainty = MatchCertainty.MATCHED
    included: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "range": self.range.to_dict(),
            "snippet": self.snippet,
            "certainty": self.certainty.value,
            "included": self.included,
        }


MATCH_SITE_CAP = 100


@dataclass(frozen=True)
class RewriteReport:
    """The result of a Rewrite: identical detail on Dry Run and Live Run.

    The Blast Radius and the total Match Site count are always complete;
    only the per-site enumeration is capped, and only loudly (unsure sites
    first — they carry the highest adjudication value).
    """

    applied: bool
    blast_radius: tuple[BlastRadiusEntry, ...]
    match_sites: tuple[MatchSite, ...]

    def to_dict(self) -> dict[str, Any]:
        shown, truncation = self._enumerate_within_cap()
        result = {
            "status": "applied" if self.applied else "dry_run",
            "summary": self._summary(),
            "match_site_count": len(self.match_sites),
            "unsure_count": self._unsure_count(),
            "match_sites": [site.to_dict() for site in shown],
            "blast_radius": [entry.to_dict() for entry in self.blast_radius],
        }
        if truncation is not None:
            result["truncation"] = truncation
        return result

    def _unsure_count(self) -> int:
        return sum(
            1 for site in self.match_sites
            if site.certainty is MatchCertainty.UNSURE
        )

    def _summary(self) -> str:
        total = len(self.match_sites)
        if total == 0:
            return "0 Match Sites — the Pattern fired nowhere in the Search Scope."
        plural = "" if total == 1 else "s"
        summary = f"{total} Match Site{plural} ({self._unsure_count()} unsure)"
        excluded_unsure = self._excluded(MatchCertainty.UNSURE)
        if excluded_unsure:
            summary += (
                f"; {excluded_unsure} unsure of those not rewritten — set the "
                "unsure Match Constraint to include them"
            )
        excluded_matched = self._excluded(MatchCertainty.MATCHED)
        if excluded_matched:
            summary += (
                f"; {excluded_matched} not rewritten because they overlap an "
                "earlier match — re-run to rewrite successive layers"
            )
        return summary + "."

    def _excluded(self, certainty: MatchCertainty) -> int:
        return sum(
            1 for site in self.match_sites
            if not site.included and site.certainty is certainty
        )

    def _enumerate_within_cap(
        self,
    ) -> tuple[tuple[MatchSite, ...], str | None]:
        total = len(self.match_sites)
        if total <= MATCH_SITE_CAP:
            return self.match_sites, None
        unsure_first = sorted(
            self.match_sites,
            key=lambda site: site.certainty is not MatchCertainty.UNSURE,
        )
        truncation = (
            f"showing {MATCH_SITE_CAP} of {total} Match Sites, unsure sites "
            "first. A truncated enumeration is an incomplete audit — tighten "
            "the Pattern or Match Constraints and re-run before a Live Run."
        )
        return tuple(unsure_first[:MATCH_SITE_CAP]), truncation


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
    INVALID_PATTERN = "invalid-pattern"
    INVALID_GOAL = "invalid-goal"
    INVALID_MATCH_CONSTRAINT = "invalid-match-constraint"
    REWRITE_WOULD_BREAK_SYNTAX = "rewrite-would-break-syntax"
    UNPARSABLE_FILE = "unparsable-file"
    INVALID_ARGUMENT = "invalid-argument"
    INTERNAL_ERROR = "internal-error"
