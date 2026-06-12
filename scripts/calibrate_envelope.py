"""Calibrate the PRD capacity & latency envelope on generated fixtures.

Generates a small and a large repository, runs a cold then warm rename
against each, and prints the operability records plus peak memory. The
warm validate() figure is the Phase 4 hook trigger (~250 ms p50).

Run: uv run python scripts/calibrate_envelope.py
"""

from __future__ import annotations

import json
import logging
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

from ropey.model import Position
from ropey.project_provider import ProjectProvider
from ropey.refactoring_runner import RefactoringRunner
from ropey.rewrite_runner import RewriteRunner

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")


def build_fixture(root: Path, module_count: int) -> None:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("anchor = 1\n")
    for index in range(module_count):
        (root / "pkg" / f"mod_{index:05d}.py").write_text(
            f"from pkg.core import anchor\nvalue_{index} = anchor + {index}\n"
        )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def measure(label: str, module_count: int) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "fixture"
        root.mkdir()
        build_fixture(root, module_count)
        runner = RefactoringRunner(ProjectProvider())
        print(f"\n=== {label}: {module_count + 2} files ===")
        for call in ("cold", "warm"):
            report = runner.rename(
                file=str(root / "pkg" / "core.py"),
                position=Position(0, 0),
                new_name=f"anchor_{call}",
                apply=False,
            )
            print(f"{call}: blast radius {len(report.blast_radius)} files")
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"peak RSS: {peak_kb / 1024:.0f} MB")


def measure_rewrite(label: str, module_count: int) -> None:
    """The Rewrite's match scan: unconstrained, and with a Match Constraint
    (which adds the extra certainty passes)."""
    import threading

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "fixture"
        root.mkdir()
        build_fixture(root, module_count)
        rewriter = RewriteRunner(ProjectProvider(), threading.Lock())
        print(f"\n=== rewrite {label}: {module_count + 2} files ===")
        for scenario, constraints in (
            ("unconstrained", None),
            ("name-constrained", {"a": {"name": "pkg.core.anchor"}}),
        ):
            report = rewriter.rewrite(
                pattern="${a} + ${i}",
                goal="${i} + ${a}",
                constraints=constraints,
                apply=False,
                root=str(root),
            )
            print(f"{scenario}: {len(report.match_sites)} match sites")


if __name__ == "__main__":
    measure("small", 50)
    measure("large", 2000)
    measure_rewrite("small", 50)
    measure_rewrite("large", 2000)
