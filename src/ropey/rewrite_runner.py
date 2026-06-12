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
from typing import Any

from rope.refactor.restructure import Restructure

from .blast_radius_reporter import report
from .engine_session import engine_session
from .match_enumerator import enumerate_match_sites
from .model import RewriteReport
from .operability import CallMetrics, Stopwatch, observed
from .project_provider import ProjectProvider
from .rewrite_language import (
    validate_constraints,
    validate_imports,
    validate_templates,
)
from .syntax_guard import ensure_parsable


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
        constraints: dict[str, dict[str, Any]] | None = None,
        imports: list[str] | None = None,
        apply: bool,
        root: str | None = None,
    ) -> RewriteReport:
        metrics = CallMetrics(tool="rewrite", event="rewrite-call")
        with observed(metrics):
            wildcards = validate_templates(pattern, goal)
            args = validate_constraints(constraints, wildcards)
            import_statements = validate_imports(imports)
            with engine_session(
                self._provider, self._lock, metrics, root=root
            ) as project:
                with Stopwatch() as match_scan:
                    changes = Restructure(
                        project,
                        pattern,
                        goal,
                        args=dict(args),
                        imports=import_statements,
                    ).get_changes()
                    match_sites = enumerate_match_sites(project, pattern, args)
                metrics.match_scan_ms = match_scan.ms
                ensure_parsable(changes)
                blast_radius = report(changes)
                if apply and blast_radius:
                    project.do(changes)
            metrics.outcome = "applied" if apply else "dry"
            return RewriteReport(
                applied=apply,
                blast_radius=blast_radius,
                match_sites=match_sites,
            )
