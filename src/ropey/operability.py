"""Operability: one structured log record per tool call.

Enough to decide the Phase 4 hook contingency (validate() timings) and to
post-mortem a surprising refactor — no metrics stack, logs only (PRD
Operability). Records go to stderr via ``logging``, never to stdout,
which belongs to the MCP stdio protocol.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from .model import StructuredFailure

logger = logging.getLogger("ropey.operability")


def configure_logging() -> None:
    """Send operability records to stderr (the MCP channel owns stdout)."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass
class CallMetrics:
    """The per-call record: timings, scope, and outcome."""

    tool: str
    event: str = "refactoring-call"
    root: str | None = None
    scope_file_count: int | None = None
    lock_wait_ms: float | None = None
    validate_ms: float | None = None
    refactoring_ms: float | None = None
    match_scan_ms: float | None = None
    outcome: str | None = None
    failure_kind: str | None = None
    _start: float = field(default_factory=time.perf_counter)

    def emit(self) -> None:
        record = {
            "event": self.event,
            "tool": self.tool,
            "root": self.root,
            "scope_file_count": self.scope_file_count,
            "lock_wait_ms": _round(self.lock_wait_ms),
            "validate_ms": _round(self.validate_ms),
            "refactoring_ms": _round(self.refactoring_ms),
            "total_ms": _round((time.perf_counter() - self._start) * 1000),
            "outcome": self.outcome,
        }
        if self.match_scan_ms is not None:
            record["match_scan_ms"] = _round(self.match_scan_ms)
        if self.failure_kind:
            record["failure_kind"] = self.failure_kind
        logger.info(json.dumps(record))


@contextmanager
def observed(metrics: CallMetrics):
    """Classify the call's outcome on failure and emit exactly one record.

    The caller sets the success outcome ("applied"/"dry") inside the block;
    any escaping exception is classified here so no path skips the record.
    """
    try:
        yield
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


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


class Stopwatch:
    """Measures one span in milliseconds."""

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info):
        self.ms = (time.perf_counter() - self._start) * 1000
        return False
