"""The uncertainty & failure contract at the tool boundary (issues #4, #5)."""

from __future__ import annotations

import json

from conftest import blast_paths

DOCUMENT = """\
class Document:
    def save(self):
        return "saved"
"""

CERTAIN_CALLER = """\
from document import Document

doc = Document()
doc.save()
"""

DYNAMIC_CALLER = """\
def persist(obj):
    obj.save()
"""


class TestUncertainOccurrences:
    def test_dynamic_call_site_is_reported_not_edited_not_dropped(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "document.py": DOCUMENT,
                "app.py": CERTAIN_CALLER,
                "dynamic.py": DYNAMIC_CALLER,
            }
        )
        report = call_tool(
            "rename",
            {
                "file": str(repo / "document.py"),
                "line": 1,
                "character": 8,
                "new_name": "persist_to_disk",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        # The uncertain site is surfaced as a flagged Location...
        occurrences = report["uncertain_occurrences"]
        assert len(occurrences) == 1
        occurrence = occurrences[0]
        assert occurrence["path"] == "dynamic.py"
        assert occurrence["line"] == 1
        assert "obj.save()" in occurrence["snippet"]
        # ...and was not silently edited.
        assert "obj.save()" in (repo / "dynamic.py").read_text()

    def test_certain_occurrences_are_still_applied_in_the_same_call(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "document.py": DOCUMENT,
                "app.py": CERTAIN_CALLER,
                "dynamic.py": DYNAMIC_CALLER,
            }
        )
        report = call_tool(
            "rename",
            {
                "file": str(repo / "document.py"),
                "line": 1,
                "character": 8,
                "new_name": "persist_to_disk",
                "apply": True,
            },
        )
        assert blast_paths(report) == {"document.py", "app.py"}
        assert "doc.persist_to_disk()" in (repo / "app.py").read_text()
        assert "def persist_to_disk(self):" in (repo / "document.py").read_text()


class TestStructuredFailures:
    def test_invalid_target_states_the_failed_precondition(
        self, make_repo, call_tool
    ):
        repo = make_repo({"mod.py": "x = 1 + 2\n"})
        report = call_tool(
            "rename",
            {
                # Position on "+": not a resolvable identifier.
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 6,
                "new_name": "y",
            },
        )
        assert report["status"] == "failure"
        failure = report["failure"]
        assert failure["kind"] == "target-not-refactorable"
        assert "Target" in failure["reason"]
        assert "Traceback" not in json.dumps(report)

    def test_broken_file_in_scope_is_named_not_skipped(self, make_repo, call_tool):
        repo = make_repo(
            {
                "lib.py": "flag = True\n",
                "app.py": "from lib import flag\nprint(flag)\n",
                # Textually mentions the name, so it cannot be silently skipped.
                "broken.py": "def oops(:\n    flag\n",
            }
        )
        report = call_tool(
            "rename",
            {
                "file": str(repo / "lib.py"),
                "line": 0,
                "character": 0,
                "new_name": "enabled",
                "apply": True,
            },
        )
        assert report["status"] == "failure"
        failure = report["failure"]
        assert failure["kind"] == "unparsable-file"
        assert "broken.py" in failure["reason"]
        # Nothing was half-applied.
        assert (repo / "lib.py").read_text() == "flag = True\n"

    def test_rope_text_rides_only_in_the_detail_field(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "x = 1 + 2\n"})
        report = call_tool(
            "rename",
            {"file": str(repo / "mod.py"), "line": 0, "character": 6, "new_name": "y"},
        )
        failure = report["failure"]
        # The engine's own phrasing stays in detail, not in the reason.
        assert "detail" in failure
        assert failure["detail"] not in failure["reason"]

    def test_unknown_file_is_a_structured_failure(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "x = 1\n"})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "missing.py"),
                "line": 0,
                "character": 0,
                "new_name": "y",
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "file-not-found"


class TestExpectedSymbolGuard:
    def test_mismatch_names_expected_versus_found(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "current = 1\nprint(current)\n"})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "new_name": "fresh",
                "expected_symbol": "stale_name",
            },
        )
        assert report["status"] == "failure"
        failure = report["failure"]
        assert failure["kind"] == "expected-symbol-mismatch"
        assert "stale_name" in failure["reason"]
        assert "current" in failure["reason"]
        assert (repo / "mod.py").read_text() == "current = 1\nprint(current)\n"

    def test_match_proceeds_normally(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "current = 1\nprint(current)\n"})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "new_name": "fresh",
                "expected_symbol": "current",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        assert "fresh = 1" in (repo / "mod.py").read_text()

    def test_omitted_guard_proceeds(self, make_repo, call_tool):
        repo = make_repo({"mod.py": "current = 1\n"})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "mod.py"),
                "line": 0,
                "character": 0,
                "new_name": "fresh",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
