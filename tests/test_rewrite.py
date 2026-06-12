"""The Rewrite sibling at the tool boundary (PRD 0002, ADR 0005).

Fixture-repository integration tests against real rope: files on disk,
Blast Radius, Match Sites, Structured Failures — never internals.
"""

from __future__ import annotations

import json
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


CONSTRAINT_FIXTURE = {
    "models.py": (
        "class Model:\n"
        "    def save(self):\n"
        "        return 'saved'\n"
        "\n"
        "\n"
        "class Audited(Model):\n"
        "    pass\n"
    ),
    "handlers.py": (
        "from models import Model\n"
        "\n"
        "record = Model()\n"
        "record.save()\n"
        "\n"
        "cache = {'a': 1}\n"
        "cache.save()\n"
    ),
    "tasks.py": "def touch(thing):\n    thing.save()\n",
}

SAVE_PATTERN = "${x}.save()"
SAVE_GOAL = "${x}.persist()"


def sites_by_path(report: dict) -> dict[str, dict]:
    return {site["path"]: site for site in report["match_sites"]}


class TestMatchConstraints:
    def test_unconstrained_pattern_matches_every_site_as_matched(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": SAVE_PATTERN, "goal": SAVE_GOAL, "root": str(repo)},
        )
        assert report["match_site_count"] == 3
        assert all(s["certainty"] == "matched" for s in report["match_sites"])
        assert all(s["included"] for s in report["match_sites"])

    def test_type_constraint_drops_the_provably_wrong_site(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"type": "models.Model"}},
                "root": str(repo),
            },
        )
        sites = sites_by_path(report)
        assert set(sites) == {"handlers.py", "tasks.py"}
        assert sites["handlers.py"]["certainty"] == "matched"
        assert sites["handlers.py"]["snippet"] == "record.save()"

    def test_unprovable_site_is_surfaced_unsure_and_not_rewritten_by_default(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"type": "models.Model"}},
                "apply": True,
                "root": str(repo),
            },
        )
        site = sites_by_path(report)["tasks.py"]
        assert site["certainty"] == "unsure"
        assert site["included"] is False
        assert report["unsure_count"] == 1
        assert "record.persist()" in (repo / "handlers.py").read_text()
        assert "cache.save()" in (repo / "handlers.py").read_text()
        assert (repo / "tasks.py").read_text() == CONSTRAINT_FIXTURE["tasks.py"]

    def test_name_constraint_narrows_to_references_of_that_symbol(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "helpers.py": (
                    "def legacy(x):\n    return x\n\n\n"
                    "def modern(x):\n    return x\n"
                ),
                "caller.py": (
                    "from helpers import legacy, modern\n\n"
                    "legacy(1)\n"
                    "modern(2)\n"
                ),
            }
        )
        report = call_tool(
            "rewrite",
            {
                "pattern": "${func}(${arg})",
                "goal": "${func}(${arg}, migrated=True)",
                "constraints": {"func": {"name": "helpers.legacy"}},
                "root": str(repo),
            },
        )
        snippets = {s["snippet"] for s in report["match_sites"] if s["included"]}
        assert "legacy(1)" in snippets
        assert "modern(2)" not in snippets

    def test_object_constraint_pins_one_class_object(self, make_repo, call_tool):
        repo = make_repo(
            {
                **CONSTRAINT_FIXTURE,
                "factories.py": (
                    "from models import Model, Audited\n\n"
                    "a = Model()\n"
                    "b = Audited()\n"
                ),
            }
        )
        report = call_tool(
            "rewrite",
            {
                "pattern": "${cls}()",
                "goal": "${cls}.create()",
                "constraints": {"cls": {"object": "models.Model"}},
                "root": str(repo),
            },
        )
        included = [s for s in report["match_sites"] if s["included"]]
        assert {s["snippet"] for s in included} == {"a = Model()", "record = Model()"}

    def test_instance_constraint_admits_subclasses_where_type_does_not(
        self, make_repo, call_tool
    ):
        fixture = {
            **CONSTRAINT_FIXTURE,
            "audit.py": (
                "from models import Audited\n\n"
                "trail = Audited()\n"
                "trail.save()\n"
            ),
        }
        repo = make_repo(fixture, name="instance_repo")
        by_type = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"type": "models.Model"}},
                "root": str(repo),
            },
        )
        assert "audit.py" not in {
            s["path"] for s in by_type["match_sites"] if s["included"]
        }
        by_instance = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"instance": "models.Model"}},
                "root": str(repo),
            },
        )
        trail = sites_by_path(by_instance)["audit.py"]
        assert trail["certainty"] == "matched"
        assert trail["included"] is True

    def test_exact_constraint_matches_only_the_literal_name(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": "${record}.save()",
                "goal": "${record}.persist()",
                "constraints": {"record": {"exact": True}},
                "root": str(repo),
            },
        )
        assert [s["snippet"] for s in report["match_sites"]] == ["record.save()"]

    def test_unknown_constraint_key_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"kind": "models.Model"}},
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-match-constraint"

    def test_constraint_on_an_unknown_wildcard_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"y": {"type": "models.Model"}},
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-match-constraint"
        assert "y" in report["failure"]["reason"]

    def test_two_narrowing_keys_on_one_wildcard_are_refused_not_silently_ranked(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {
                    "x": {"type": "models.Model", "name": "handlers.record"}
                },
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-match-constraint"

    def test_the_published_surface_never_says_proven(self, make_repo, call_tool):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"type": "models.Model"}},
                "root": str(repo),
            },
        )
        assert "proven" not in json.dumps(report)


class TestUnsureKnob:
    def test_unsure_includes_the_unprovable_site_and_keeps_it_flagged(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": SAVE_GOAL,
                "constraints": {"x": {"type": "models.Model", "unsure": True}},
                "apply": True,
                "root": str(repo),
            },
        )
        site = sites_by_path(report)["tasks.py"]
        assert site["certainty"] == "unsure"
        assert site["included"] is True
        assert (repo / "tasks.py").read_text() == (
            "def touch(thing):\n    thing.persist()\n"
        )
        assert "cache.save()" in (repo / "handlers.py").read_text()

    def test_unsure_is_per_wildcard_not_global(self, make_repo, call_tool):
        repo = make_repo(
            {
                "models.py": CONSTRAINT_FIXTURE["models.py"],
                "sync.py": (
                    "from models import Model\n"
                    "\n"
                    "known = Model()\n"
                    "\n"
                    "\n"
                    "def relay(source, target):\n"
                    "    source.copy_to(known)\n"
                    "    source.copy_to(target)\n"
                ),
            }
        )
        report = call_tool(
            "rewrite",
            {
                "pattern": "${src}.copy_to(${dst})",
                "goal": "${dst}.copy_from(${src})",
                "constraints": {
                    "src": {"type": "models.Model", "unsure": True},
                    "dst": {"type": "models.Model"},
                },
                "apply": True,
                "root": str(repo),
            },
        )
        text = (repo / "sync.py").read_text()
        # src is unprovable but pre-adjudicated; dst stays strict, so only
        # the call whose target is provably a Model is rewritten.
        assert "known.copy_from(source)" in text
        assert "source.copy_to(target)" in text
        sites = report["match_sites"]
        assert len(sites) == 2
        included = [s for s in sites if s["included"]]
        assert len(included) == 1
        assert all(s["certainty"] == "unsure" for s in sites)

    def test_dry_and_live_runs_agree_on_what_the_knob_includes(
        self, make_repo, call_tool
    ):
        repo = make_repo(CONSTRAINT_FIXTURE)
        arguments = {
            "pattern": SAVE_PATTERN,
            "goal": SAVE_GOAL,
            "constraints": {"x": {"type": "models.Model", "unsure": True}},
            "root": str(repo),
        }
        dry = call_tool("rewrite", arguments)
        live = call_tool("rewrite", {**arguments, "apply": True})
        assert dry["match_sites"] == live["match_sites"]
        assert dry["blast_radius"] == live["blast_radius"]


SYNTAX_BREAK_FIXTURE = {
    "store.py": "record = object()\nvalue = record.save()\n",
}

# Parses standalone, but substituted into the expression context of
# ``value = record.save()`` it yields ``value = if record: ...`` — broken.
BREAKING_GOAL = "if ${x}:\n    pass"


class TestSyntaxGuard:
    def test_a_syntax_breaking_goal_fails_at_dry_run_naming_the_parse_location(
        self, make_repo, call_tool
    ):
        repo = make_repo(SYNTAX_BREAK_FIXTURE)
        report = call_tool(
            "rewrite",
            {"pattern": SAVE_PATTERN, "goal": BREAKING_GOAL, "root": str(repo)},
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "rewrite-would-break-syntax"
        assert "store.py" in report["failure"]["reason"]
        assert "line" in report["failure"]["reason"]
        assert (repo / "store.py").read_text() == SYNTAX_BREAK_FIXTURE["store.py"]

    def test_a_cold_live_run_fails_the_same_way_with_nothing_written(
        self, make_repo, call_tool
    ):
        repo = make_repo(SYNTAX_BREAK_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": SAVE_PATTERN,
                "goal": BREAKING_GOAL,
                "apply": True,
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "rewrite-would-break-syntax"
        assert (repo / "store.py").read_text() == SYNTAX_BREAK_FIXTURE["store.py"]


IMPORTS_FIXTURE = {
    "helpers.py": "def migrate(value):\n    return value\n",
    "app.py": "record = object()\nrecord.old_style()\n",
    "already.py": (
        "from helpers import migrate\n"
        "\n"
        "item = object()\n"
        "item.old_style()\n"
    ),
}

OLD_STYLE_PATTERN = "${x}.old_style()"
MIGRATE_GOAL = "migrate(${x})"
MIGRATE_IMPORT = "from helpers import migrate"


class TestImports:
    def test_supplied_imports_are_added_to_each_changed_module(
        self, make_repo, call_tool
    ):
        repo = make_repo(IMPORTS_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": OLD_STYLE_PATTERN,
                "goal": MIGRATE_GOAL,
                "imports": [MIGRATE_IMPORT],
                "apply": True,
                "root": str(repo),
            },
        )
        app = (repo / "app.py").read_text()
        assert MIGRATE_IMPORT in app
        assert "migrate(record)" in app
        assert (repo / "helpers.py").read_text() == IMPORTS_FIXTURE["helpers.py"]
        assert "app.py" in blast_paths(report)

    def test_an_already_present_import_is_not_doubled(self, make_repo, call_tool):
        repo = make_repo(IMPORTS_FIXTURE)
        call_tool(
            "rewrite",
            {
                "pattern": OLD_STYLE_PATTERN,
                "goal": MIGRATE_GOAL,
                "imports": [MIGRATE_IMPORT],
                "apply": True,
                "root": str(repo),
            },
        )
        already = (repo / "already.py").read_text()
        assert already.count(MIGRATE_IMPORT) == 1
        assert "migrate(item)" in already

    def test_no_import_inference_omitting_imports_leaves_them_absent(
        self, make_repo, call_tool
    ):
        repo = make_repo(IMPORTS_FIXTURE)
        call_tool(
            "rewrite",
            {
                "pattern": OLD_STYLE_PATTERN,
                "goal": MIGRATE_GOAL,
                "apply": True,
                "root": str(repo),
            },
        )
        app = (repo / "app.py").read_text()
        assert "migrate(record)" in app
        assert "import" not in app

    def test_a_non_import_entry_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo(IMPORTS_FIXTURE)
        report = call_tool(
            "rewrite",
            {
                "pattern": OLD_STYLE_PATTERN,
                "goal": MIGRATE_GOAL,
                "imports": ["x = 1"],
                "root": str(repo),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "invalid-argument"


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


class TestNonAsciiMatchSites:
    # The emoji is astral (2 UTF-16 units per code point); the CJK
    # identifiers are BMP. Characters before the match on its line:
    # 'banner = "<2x emoji>"; <CJK> = ' -> 17 + 4 = 21 UTF-16 units.
    UNICODE_LINE = 'banner = "\U0001f40d\U0001f40d"; 値 = conf.get_attribute("名前")'

    def fixture(self):
        return {"unicode.py": f"{self.UNICODE_LINE}\n"}

    def assert_utf16_range(self, report: dict) -> None:
        site = site_for(report, "unicode.py")
        assert site["range"]["start"] == {"line": 0, "character": 21}
        assert site["range"]["end"] == {"line": 0, "character": 45}

    def test_a_match_after_emoji_and_cjk_reports_a_correct_utf16_range(
        self, make_repo, call_tool
    ):
        repo = make_repo(self.fixture())
        report = call_tool(
            "rewrite", {"pattern": PATTERN, "goal": GOAL, "root": str(repo)}
        )
        self.assert_utf16_range(report)

    def test_live_run_ranges_address_the_pre_apply_text(
        self, make_repo, call_tool
    ):
        repo = make_repo(self.fixture())
        report = call_tool(
            "rewrite",
            {"pattern": PATTERN, "goal": GOAL, "apply": True, "root": str(repo)},
        )
        self.assert_utf16_range(report)
        assert 'conf["名前"]' in (repo / "unicode.py").read_text()


def truncation_fixture() -> dict[str, str]:
    """125 Match Sites under type=Model: 110 provable, 15 unsure."""
    certain = "\n".join("record.save()" for _ in range(110))
    unsure = "\n".join("    thing.save()" for _ in range(15))
    return {
        "models.py": CONSTRAINT_FIXTURE["models.py"],
        "bulk.py": f"from models import Model\n\nrecord = Model()\n{certain}\n",
        "dynamic.py": f"def churn(thing):\n{unsure}\n",
    }


class TestLoudTruncation:
    ARGUMENTS = {
        "pattern": SAVE_PATTERN,
        "goal": SAVE_GOAL,
        "constraints": {"x": {"type": "models.Model"}},
    }

    def test_an_over_cap_match_set_is_truncated_loudly(self, make_repo, call_tool):
        repo = make_repo(truncation_fixture())
        report = call_tool("rewrite", {**self.ARGUMENTS, "root": str(repo)})
        assert report["match_site_count"] == 125
        assert report["unsure_count"] == 15
        assert len(report["match_sites"]) == 100
        assert "showing 100 of 125" in report["truncation"]

    def test_unsure_sites_are_listed_first_when_truncated(
        self, make_repo, call_tool
    ):
        repo = make_repo(truncation_fixture())
        report = call_tool("rewrite", {**self.ARGUMENTS, "root": str(repo)})
        leading = report["match_sites"][:15]
        assert all(site["certainty"] == "unsure" for site in leading)
        assert all(
            site["certainty"] == "matched" for site in report["match_sites"][15:]
        )

    def test_blast_radius_is_complete_despite_truncation(
        self, make_repo, call_tool
    ):
        repo = make_repo(truncation_fixture())
        report = call_tool("rewrite", {**self.ARGUMENTS, "root": str(repo)})
        assert blast_paths(report) == {"bulk.py"}

    def test_live_run_over_cap_applies_every_match_not_just_the_shown_ones(
        self, make_repo, call_tool
    ):
        repo = make_repo(truncation_fixture())
        call_tool("rewrite", {**self.ARGUMENTS, "apply": True, "root": str(repo)})
        bulk = (repo / "bulk.py").read_text()
        assert bulk.count("record.persist()") == 110
        assert "record.save()" not in bulk

    def test_under_cap_enumeration_is_complete_and_unflagged(
        self, make_repo, call_tool
    ):
        repo = make_repo(GET_ATTRIBUTE_FIXTURE)
        report = call_tool(
            "rewrite", {"pattern": PATTERN, "goal": GOAL, "root": str(repo)}
        )
        assert len(report["match_sites"]) == report["match_site_count"]
        assert "truncation" not in report


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
