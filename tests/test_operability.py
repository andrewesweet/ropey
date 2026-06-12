"""Operability logging: one structured record per call (issue #6)."""

from __future__ import annotations

import json
import logging


def last_record(caplog) -> dict:
    lines = [r.message for r in caplog.records if r.name == "ropey.operability"]
    assert lines, "no operability record emitted"
    return json.loads(lines[-1])


class TestPerCallLogging:
    def test_successful_call_emits_one_complete_record(
        self, make_repo, call_tool, caplog
    ):
        repo = make_repo({"mod.py": "value = 1\nprint(value)\n"})
        with caplog.at_level(logging.INFO, logger="ropey.operability"):
            call_tool(
                "rename",
                {
                    "file": str(repo / "mod.py"),
                    "line": 0,
                    "character": 0,
                    "new_name": "amount",
                    "apply": True,
                },
            )
        record = last_record(caplog)
        assert record["event"] == "refactoring-call"
        assert record["tool"] == "rename"
        assert record["root"] == str(repo)
        assert record["scope_file_count"] >= 1
        for timing in ("lock_wait_ms", "validate_ms", "refactoring_ms", "total_ms"):
            assert isinstance(record[timing], (int, float))
        assert record["outcome"] == "applied"

    def test_dry_run_and_failure_outcomes_are_distinguished(
        self, make_repo, call_tool, caplog
    ):
        repo = make_repo({"mod.py": "value = 1\n"})
        with caplog.at_level(logging.INFO, logger="ropey.operability"):
            call_tool(
                "rename",
                {
                    "file": str(repo / "mod.py"),
                    "line": 0,
                    "character": 0,
                    "new_name": "amount",
                },
            )
            dry = last_record(caplog)
            call_tool(
                "rename",
                {
                    "file": str(repo / "mod.py"),
                    "line": 0,
                    "character": 4,
                    "new_name": "amount",
                    "expected_symbol": "other",
                },
            )
            failed = last_record(caplog)
        assert dry["outcome"] == "dry"
        assert failed["outcome"] == "failure"
        assert failed["failure_kind"] == "expected-symbol-mismatch"
