"""Refactoring Runner: executes one Refactoring under the transaction model.

Owns the serial-execution lock (the per-root Project's consistency
boundary — rope Projects are not thread-safe), the Dry Run / Live Run
``apply`` flag, and the shared call skeleton every tool goes through:

    lock -> resolve root -> fresh Project -> translate Location ->
    build ChangeSet -> report Blast Radius -> apply (Live Run only)

rope types flow freely here (ADR 0004) but never cross into tool inputs
or outputs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from rope.base.change import Change
from rope.base.project import Project
from rope.refactor.rename import Rename

from .blast_radius_reporter import report
from .failure_mapper import map_engine_failures
from .location_translator import (
    check_expected_symbol,
    offset_to_position,
    position_to_offset,
)
from .model import (
    Position,
    RefactoringReport,
    StructuredFailure,
    UncertainOccurrence,
)
from .operability import CallMetrics, Stopwatch
from .project_provider import ProjectProvider


class UncertainOccurrenceCollector:
    """Collects rope's unsure occurrences as flagged Locations.

    Wired as the ``unsure`` callback: returning False keeps every uncertain
    occurrence out of the Change Set (never silently included) while the
    collection surfaces each one in the result (never silently dropped).
    """

    def __init__(self):
        self.occurrences: list[UncertainOccurrence] = []

    def __call__(self, occurrence) -> bool:
        start, _ = occurrence.get_word_range()
        text = occurrence.resource.read()
        position = offset_to_position(text, start)
        snippet = text.split("\n")[position.line].strip()
        self.occurrences.append(
            UncertainOccurrence(
                path=occurrence.resource.path,
                position=position,
                snippet=snippet,
            )
        )
        return False


class RefactoringRunner:
    """Runs each Refactoring of the catalogue against a fresh, scoped Project."""

    def __init__(self, provider: ProjectProvider):
        self._provider = provider
        self._lock = threading.Lock()

    # -- the shared call skeleton -------------------------------------------

    def _execute(
        self,
        *,
        tool: str,
        file: str | None,
        root: str | None,
        apply: bool,
        build: Callable[[Project, object, UncertainOccurrenceCollector], Change],
    ) -> RefactoringReport:
        metrics = CallMetrics(tool=tool)
        try:
            with Stopwatch() as lock_wait:
                self._lock.acquire()
            metrics.lock_wait_ms = lock_wait.ms
            try:
                scope_root = self._provider.resolve_root(file, root)
                metrics.root = str(scope_root)
                with map_engine_failures():
                    project = self._provider.get_project(scope_root, metrics)
                    resource = (
                        self._provider.resource_for(project, file)
                        if file is not None
                        else None
                    )
                    collector = UncertainOccurrenceCollector()
                    with Stopwatch() as refactoring:
                        changes = build(project, resource, collector)
                        blast_radius = report(changes)
                        if apply:
                            project.do(changes)
                    metrics.refactoring_ms = refactoring.ms
            finally:
                self._lock.release()
            metrics.outcome = "applied" if apply else "dry"
            return RefactoringReport(
                applied=apply,
                blast_radius=blast_radius,
                uncertain_occurrences=tuple(collector.occurrences),
            )
        except StructuredFailure as failure:
            metrics.outcome = "failure"
            metrics.failure_kind = failure.kind
            raise
        except Exception:
            metrics.outcome = "failure"
            metrics.failure_kind = "internal-error"
            raise
        finally:
            metrics.emit()

    def _point_offset(
        self, resource, position: Position, expected_symbol: str | None
    ) -> int:
        text = resource.read()
        offset = position_to_offset(text, position)
        if expected_symbol is not None:
            check_expected_symbol(text, offset, expected_symbol)
        return offset

    # -- the catalogue -------------------------------------------------------

    def rename(
        self,
        *,
        file: str,
        position: Position,
        new_name: str,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        in_docstrings_and_comments: bool = False,
        across_class_hierarchy: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = Rename(project, resource, offset)
            return refactoring.get_changes(
                new_name,
                docs=in_docstrings_and_comments,
                in_hierarchy=across_class_hierarchy,
                unsure=collector,
            )

        return self._execute(
            tool="rename", file=file, root=root, apply=apply, build=build
        )
