"""The Rewrite sibling at the tool boundary (PRD 0002, ADR 0005).

Fixture-repository integration tests against real rope: files on disk,
Blast Radius, Match Sites, Structured Failures — never internals.
"""

from __future__ import annotations

import logging

from conftest import blast_paths, entry_for
from test_operability import last_record

GET_ATTRIBUTE_FIXTURE = {
    "settings.py": (
        "class Config:\n"
        "    def get_attribute(self, key):\n"
        "        return getattr(self, key)\n"
    ),
    "app.py": (
        "from settings import Config\n"
        "\n"
        "cfg = Config()\n"
        'name = cfg.get_attribute("name")\n'
    ),
    "jobs.py": (
        "from settings import Config\n"
        "\n"
        "job_cfg = Config()\n"
        'role = job_cfg.get_attribute("role")\n'
    ),
}

PATTERN = "${conf}.get_attribute(${key})"
GOAL = "${conf}[${key}]"


def site_for(report: dict, path: str) -> dict:
    matches = [s for s in report["match_sites"] if s["path"] == path]
    assert matches, f"{path} not in match sites: {report['match_sites']}"
    return matches[0]


class TestPatternGoalRewrite:
    def test_live_run_rewrites_exactly_the_matched_sites(self, make_repo, call_tool):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        assert report["status"] == "applied"
        assert (repo / "app.py").read_text().splitlines()[3] == 'name = cfg["name"]'
        assert (
            repo / "jobs.py"
        ).read_text().splitlines()[3] == 'role = job_cfg["role"]'
        assert "get_attribute" in (repo / "settings.py").read_text()

    def test_blast_radius_reports_modified_files_only(self, make_repo, call_tool):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        assert blast_paths(report) == {"app.py", "jobs.py"}
        assert entry_for(report, "app.py")["change_kind"] == "modified"

    def test_match_sites_carry_pre_apply_lsp_ranges(self, make_repo, call_tool):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        assert report["match_site_count"] == 2
        site = site_for(report, "app.py")
        # Line 3 pre-apply: name = cfg.get_attribute("name")
        assert site["range"]["start"] == {"line": 3, "character": 7}
        assert site["range"]["end"] == {"line": 3, "character": 32}
        assert site["snippet"] == 'name = cfg.get_attribute("name")'

    def test_dry_run_writes_nothing_and_reports_what_live_run_reports(
        self, make_repo, call_tool
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        dry = call_tool(
            "rewrite", {"pattern": PATTERN, "goal": GOAL, "root": str(repo)}
        )
        assert dry["status"] == "dry_run"
        assert (repo / "app.py").read_text() == GET_ATTRIBUTE_FIXTURE["app.py"]
        live = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        assert live["match_sites"] == dry["match_sites"]
        assert live["blast_radius"] == dry["blast_radius"]


class TestZeroMatches:
    def test_zero_matches_is_a_loud_successful_empty_result(
        self, make_repo, call_tool
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": "${x}.no_such_method(${y})",
                "goal": "${x}.other(${y})",
                "apply": True,
                "root": str(repo),
            },
        )
        assert report["status"] == "applied"
        assert "0 Match Sites" in report["summary"]
        assert report["match_site_count"] == 0
        assert report["match_sites"] == []
        assert report["blast_radius"] == []


class TestMalformedTemplates:
    def test_unparsable_pattern_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": "def ${x}(:", "goal": "${x}", "root": str(repo)},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-pattern"
        assert "parse" in report["failure"]["reason"]

    def test_pattern_without_wildcards_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": "plain_call()", "goal": "other_call()", "root": str(repo)},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-pattern"
        assert "wildcard" in report["failure"]["reason"]

    def test_goal_referencing_an_unknown_wildcard_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": "${conf}.get_attribute(${key})",
                "goal": "${conf}[${missing}]",
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-goal"
        assert "missing" in report["failure"]["reason"]

    def test_unparsable_goal_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": "${conf}.get_attribute(${key})", "goal": "${conf}[(", "root": str(repo)},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-goal"


class TestSearchScope:
    def test_gitignored_textual_match_is_neither_matched_nor_reported(
        self, make_repo, call_tool
    ):
        generated = 'out = cfg.get_attribute("name")\n'
        repo = make_repo(
            {
                **GET_ATTRIBUTE_FIXTURE,
                ".gitignore": "generated/\n",
                "generated/gen.py": generated,
            }
        )
        report = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        assert blast_paths(report) == {"app.py", "jobs.py"}
        assert {s["path"] for s in report["match_sites"]} == {"app.py", "jobs.py"}
        assert (repo / "generated/gen.py").read_text() == generated


class TestOperability:
    def test_per_call_record_includes_match_scan_ms(
        self, make_repo, call_tool, caplog
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        with caplog.at_level(logging.INFO, logger="ropey.operability"):
            call_tool(
                "rewrite", {"pattern": PATTERN, "goal": GOAL, "root": str(repo)}
            )
        record = last_record(caplog)
        assert record["event"] == "rewrite-call"
        assert record["tool"] == "rewrite"
        assert isinstance(record["match_scan_ms"], (int, float))
        assert record["outcome"] == "dry"
