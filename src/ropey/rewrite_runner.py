"""Rewrite Runner: executes the Rewrite sibling under the transaction model.

Same call skeleton as the Refactoring Runner — lock -> resolve root ->
fresh Project -> compute Change Set -> report -> apply (Live Run only) —
but addressed by a Pattern and Goal rather than a Location, and reporting
every Match Site beside the file-level Blast Radius (ADR 0005). The lock
is shared with the Refactoring Runner: rope Projects are not thread-safe,
so the whole engine runs one call at a time.

rope types flow freely here (ADR 0004) but never cross into tool inputs
or outputs; Pattern, Goal, and Wildcard cross verbatim (Conformist).
"""

from __future__ import annotations

import threading

from rope.refactor.restructure import Restructure

from .blast_radius_reporter import report
from .failure_mapper import map_engine_failures
from .match_enumerator import enumerate_match_sites
from .model import RewriteReport
from .operability import CallMetrics, Stopwatch, observed
from .project_provider import ProjectProvider
from .rewrite_language import validate_templates


class RewriteRunner:
    """Runs a Rewrite against a fresh, scoped Project."""

    def __init__(self, provider: ProjectProvider, lock: threading.Lock):
        self._provider = provider
        self._lock = lock

    def rewrite(
        self,
        *,
        pattern: str,
        goal: str,
        apply: bool,
        root: str | None = None,
    ) -> RewriteReport:
        metrics = CallMetrics(tool="rewrite", event="rewrite-call")
        with observed(metrics):
            validate_templates(pattern, goal)
            with Stopwatch() as lock_wait:
                self._lock.acquire()
            try:
                metrics.lock_wait_ms = lock_wait.ms
                scope_root = self._provider.resolve_root(None, root)
                metrics.root = str(scope_root)
                with map_engine_failures():
                    project = self._provider.get_project(scope_root, metrics)
                    with Stopwatch() as match_scan:
                        changes = Restructure(
                            project, pattern, goal
                        ).get_changes()
                        match_sites = enumerate_match_sites(project, pattern)
                    metrics.match_scan_ms = match_scan.ms
                    blast_radius = report(changes)
                    if apply and blast_radius:
                        project.do(changes)
            finally:
                self._lock.release()
            metrics.outcome = "applied" if apply else "dry"
            return RewriteReport(
                applied=apply,
                blast_radius=blast_radius,
                match_sites=match_sites,
            )
