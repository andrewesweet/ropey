"""Search Scope hardening at the tool boundary (issue #3)."""

from __future__ import annotations

from conftest import blast_paths

LIB = "token = 1\n"
USER = "from lib import token\nprint(token)\n"


def rename_token(call_tool, repo, **overrides):
    args = {
        "file": str(repo / "lib.py"),
        "line": 0,
        "character": 0,
        "new_name": "secret",
        "apply": True,
    }
    args.update(overrides)
    return call_tool("rename", args)


class TestGitignoreExclusions:
    def test_gitignored_match_is_neither_edited_nor_reported(
        self, make_repo, call_tool
    ):
        ignored = "from lib import token\nprint(token)\n"
        repo = make_repo(
            {
                "lib.py": LIB,
                "app.py": USER,
                ".gitignore": "my-odd-venv/\n",
                "my-odd-venv/site.py": ignored,
            }
        )
        report = rename_token(call_tool, repo)
        assert report["status"] == "applied"
        assert blast_paths(report) == {"lib.py", "app.py"}
        assert (repo / "my-odd-venv" / "site.py").read_text() == ignored

    def test_unignoring_the_same_file_brings_it_into_scope(
        self, make_repo, call_tool
    ):
        repo = make_repo(
            {
                "lib.py": LIB,
                ".gitignore": "extras/\n",
                "extras/use.py": "from lib import token\nprint(token)\n",
            }
        )
        first = rename_token(call_tool, repo, new_name="first", apply=False)
        assert "extras/use.py" not in blast_paths(first)
        (repo / ".gitignore").write_text("", encoding="utf-8")
        second = rename_token(call_tool, repo, new_name="second", apply=False)
        assert "extras/use.py" in blast_paths(second)

    def test_nested_gitignore_and_negation_apply(self, make_repo, call_tool):
        repo = make_repo(
            {
                "lib.py": LIB,
                ".gitignore": "*.gen.py\n",
                "sub/.gitignore": "!keep.gen.py\nlocal_only.py\n",
                "sub/__init__.py": "",
                "sub/keep.gen.py": "from lib import token\nprint(token)\n",
                "sub/other.gen.py": "from lib import token\n",
                "sub/local_only.py": "from lib import token\n",
            }
        )
        report = rename_token(call_tool, repo, apply=False)
        paths = blast_paths(report)
        assert "sub/keep.gen.py" in paths  # negated back into scope
        assert "sub/other.gen.py" not in paths
        assert "sub/local_only.py" not in paths

    def test_no_gitignore_falls_back_to_rope_defaults(self, make_repo, call_tool):
        # Explicit root, no git repo at all: rope's default exclusions
        # (e.g. .venv, .tox) still apply.
        repo = make_repo(
            {
                "lib.py": LIB,
                "app.py": USER,
                ".venv/lib.py": "from lib import token\n",
            },
            git=False,
        )
        report = rename_token(call_tool, repo, root=str(repo), apply=False)
        paths = blast_paths(report)
        assert "app.py" in paths
        assert ".venv/lib.py" not in paths


class TestRootHandling:
    def test_explicit_root_override_is_honoured(self, make_repo, call_tool):
        repo = make_repo(
            {
                "service_a/lib.py": LIB,
                "service_a/app.py": USER,
                "service_b/use.py": "import nothing\n",
            }
        )
        report = call_tool(
            "rename",
            {
                "file": str(repo / "service_a" / "lib.py"),
                "line": 0,
                "character": 0,
                "new_name": "secret",
                "apply": True,
                "root": str(repo / "service_a"),
            },
        )
        assert report["status"] == "applied"
        assert blast_paths(report) == {"lib.py", "app.py"}

    def test_typoed_root_is_rejected_and_not_created(self, make_repo, call_tool):
        repo = make_repo({"lib.py": LIB})
        typo = repo.parent / "repo-tpyo"
        report = rename_token(call_tool, repo, root=str(typo))
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "root-not-found"
        assert not typo.exists()

    def test_no_git_ancestor_and_no_root_requests_a_root(
        self, make_repo, call_tool
    ):
        repo = make_repo({"lib.py": LIB}, git=False)
        report = rename_token(call_tool, repo)
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "root-required"
        assert "root" in report["failure"]["reason"]

    def test_file_outside_the_root_is_a_structured_failure(
        self, make_repo, call_tool
    ):
        repo = make_repo({"sub/lib.py": LIB, "outside.py": "x = 1\n"})
        report = call_tool(
            "rename",
            {
                "file": str(repo / "outside.py"),
                "line": 0,
                "character": 0,
                "new_name": "y",
                "root": str(repo / "sub"),
            },
        )
        assert report["status"] == "failure"
        assert report["failure"]["kind"] == "file-out-of-scope"
