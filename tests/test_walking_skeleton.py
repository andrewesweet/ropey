"""Walking skeleton: Rename end-to-end through every foundation seam (issue #2)."""

from __future__ import annotations

import threading

from conftest import blast_paths, entry_for

GREETER = '''\
def greet(name):
    return f"hello {name}"
'''

CALLER = """\
from greeter import greet

print(greet("world"))
"""


def repo_files():
    return {"greeter.py": GREETER, "app.py": CALLER}


def rename_args(repo, **overrides):
    args = {
        "file": str(repo / "greeter.py"),
        "line": 0,
        "character": 4,
        "new_name": "salute",
        "apply": False,
    }
    args.update(overrides)
    return args


class TestDryRunAndLiveRun:
    def test_dry_run_reports_full_blast_radius_and_writes_nothing(
        self, make_repo, call_tool
    ):
        repo = make_repo(repo_files())
        report = call_tool("rename", rename_args(repo))
        assert report["status"] == "dry_run"
        assert blast_paths(report) == {"greeter.py", "app.py"}
        for entry in report["blast_radius"]:
            assert entry["change_kind"] == "modified"
            assert entry["description"]
        assert (repo / "greeter.py").read_text() == GREETER
        assert (repo / "app.py").read_text() == CALLER

    def test_live_run_applies_every_certain_reference(self, make_repo, call_tool):
        repo = make_repo(repo_files())
        report = call_tool("rename", rename_args(repo, apply=True))
        assert report["status"] == "applied"
        assert blast_paths(report) == {"greeter.py", "app.py"}
        assert "def salute(name):" in (repo / "greeter.py").read_text()
        app = (repo / "app.py").read_text()
        assert "from greeter import salute" in app
        assert "salute(\"world\")" in app
        assert "greet(" not in app

    def test_dry_run_and_live_run_report_identical_detail(self, make_repo, call_tool):
        repo = make_repo(repo_files())
        dry = call_tool("rename", rename_args(repo))
        live = call_tool("rename", rename_args(repo, apply=True))
        assert dry["blast_radius"] == live["blast_radius"]
        assert dry["uncertain_occurrences"] == live["uncertain_occurrences"]


class TestProjectAndScope:
    def test_root_discovery_walks_up_to_the_git_root(self, make_repo, call_tool):
        repo = make_repo(
            {
                "pkg_a/__init__.py": "",
                "pkg_a/core.py": "value = 1\n",
                "pkg_b/__init__.py": "",
                "pkg_b/use.py": "from pkg_a.core import value\nprint(value)\n",
            }
        )
        report = call_tool(
            "rename",
            {
                "file": str(repo / "pkg_a" / "core.py"),
                "line": 0,
                "character": 0,
                "new_name": "amount",
                "apply": True,
            },
        )
        assert report["status"] == "applied"
        # The sibling package is only reachable if the scope is the .git root.
        assert "pkg_b/use.py" in blast_paths(report)
        assert "amount" in (repo / "pkg_b" / "use.py").read_text()

    def test_no_cache_artifact_appears_in_the_repo(self, make_repo, call_tool):
        repo = make_repo(repo_files())
        call_tool("rename", rename_args(repo, apply=True))
        artifacts = [p for p in repo.rglob(".ropeproject")]
        assert artifacts == []

    def test_out_of_band_edit_is_reflected_without_host_notification(
        self, make_repo, call_tool
    ):
        repo = make_repo(repo_files())
        first = call_tool("rename", rename_args(repo))
        assert blast_paths(first) == {"greeter.py", "app.py"}
        # Simulate another editor / git / formatter writing directly to disk.
        (repo / "other.py").write_text(
            "from greeter import greet\ngreet('again')\n", encoding="utf-8"
        )
        second = call_tool("rename", rename_args(repo))
        assert "other.py" in blast_paths(second)


class TestLocationTranslation:
    def test_non_ascii_line_targets_the_correct_character(
        self, make_repo, call_tool
    ):
        # "💚 = 2 UTF-16 units" — an emoji assignment before the target on
        # the same line shifts UTF-16 columns away from code points.
        source = '価格 = 0\ndata = {"\U0001f49a": 1}; total = data\nprint(total)\n'
        repo = make_repo({"cjk.py": source})
        # "total" on line 1: code points before it = 22, but UTF-16 units = 23.
        line = source.split("\n")[1]
        utf16_col = len(line[: line.index("total")].encode("utf-16-le")) // 2
        report = call_tool(
            "rename",
            {
                "file": str(repo / "cjk.py"),
                "line": 1,
                "character": utf16_col,
                "new_name": "grand_total",
                "apply": True,
                "expected_symbol": "total",
            },
        )
        assert report["status"] == "applied"
        text = (repo / "cjk.py").read_text(encoding="utf-8")
        assert "grand_total = data" in text
        assert "print(grand_total)" in text


class TestSerialExecution:
    def test_concurrent_calls_queue_and_never_interleave(self, make_repo, call_tool):
        files = {
            f"mod_{i}.py": f"name_{i} = {i}\nprint(name_{i})\n" for i in range(4)
        }
        repo = make_repo(files)
        reports: dict[int, dict] = {}

        def worker(i: int):
            reports[i] = call_tool(
                "rename",
                {
                    "file": str(repo / f"mod_{i}.py"),
                    "line": 0,
                    "character": 0,
                    "new_name": f"renamed_{i}",
                    "apply": True,
                },
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for i in range(4):
            assert reports[i]["status"] == "applied"
            text = (repo / f"mod_{i}.py").read_text()
            assert f"renamed_{i} = {i}" in text
            assert f"print(renamed_{i})" in text
