"""Engine Session: the transaction preamble every tool call runs inside.

One context manager shared by the Refactoring Runner and the Rewrite
Runner: take the engine lock (rope Projects are not thread-safe, so the
whole engine runs one call at a time), resolve the Search Scope root,
serve a fresh scoped Project, and translate any engine refusal into a
Structured Failure. The lock-wait time and root land on the call's
metrics record.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

from .failure_mapper import map_engine_failures
from .operability import CallMetrics, Stopwatch
from .project_provider import ProjectProvider


@contextmanager
def engine_session(
    provider: ProjectProvider,
    lock: threading.Lock,
    metrics: CallMetrics,
    *,
    file: str | None = None,
    root: str | None = None,
):
    with Stopwatch() as lock_wait:
        lock.acquire()
    try:
        metrics.lock_wait_ms = lock_wait.ms
        scope_root = provider.resolve_root(file, root)
        metrics.root = str(scope_root)
        with map_engine_failures():
            yield provider.get_project(scope_root, metrics)
    finally:
        lock.release()
