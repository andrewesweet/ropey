"""Pure unit coverage for the Scope Resolver (issue #3).

The resolver is plain policy over plain data — no filesystem here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ropey.model import StructuredFailure
from ropey.scope_resolver import ExclusionPolicy, discover_root, require_root


class TestExclusionPolicy:
    def test_simple_directory_pattern_excludes_the_tree(self):
        p = ExclusionPolicy({"": "build/\n"})
        assert p.is_excluded("build", is_directory=True)
        assert p.is_excluded("build/lib.py")
        assert p.is_excluded("build/deep/nested.py")
        assert not p.is_excluded("src/lib.py")

    def test_negation_pattern_restores_a_match(self):
        p = ExclusionPolicy({"": "*.log\n!keep.log\n"})
        assert p.is_excluded("debug.log")
        assert not p.is_excluded("keep.log")

    def test_nested_gitignore_applies_only_below_its_directory(self):
        p = ExclusionPolicy({"sub": "secret.py\n"})
        assert p.is_excluded("sub/secret.py")
        assert not p.is_excluded("secret.py")
        assert not p.is_excluded("other/secret.py")

    def test_nested_gitignore_negation_overrides_outer_pattern(self):
        p = ExclusionPolicy({"": "*.gen.py\n", "sub": "!keep.gen.py\n"})
        assert p.is_excluded("top.gen.py")
        assert p.is_excluded("sub/other.gen.py")
        assert not p.is_excluded("sub/keep.gen.py")

    def test_anchored_pattern_matches_only_at_its_gitignore_level(self):
        p = ExclusionPolicy({"": "/generated.py\n"})
        assert p.is_excluded("generated.py")
        assert not p.is_excluded("pkg/generated.py")

    def test_file_inside_excluded_directory_stays_excluded(self):
        # A .gitignore inside an ignored tree cannot re-include its parent.
        p = ExclusionPolicy({"": "vendor/\n", "vendor": "!everything\n"})
        assert p.is_excluded("vendor/everything")

    def test_git_directory_is_always_excluded(self):
        p = ExclusionPolicy({})
        assert p.is_excluded(".git/config")
        assert p.is_excluded("sub/.git/HEAD")

    def test_empty_policy_excludes_nothing_else(self):
        p = ExclusionPolicy({})
        assert not p.is_excluded("anything.py")
        assert not p.is_excluded("deep/path/file.py")


class TestRootDiscovery:
    def test_walks_up_to_the_nearest_git_ancestor(self):
        root = Path("/work/repo")
        has_git = lambda p: p == root
        assert discover_root(Path("/work/repo/pkg/sub"), has_git) == root

    def test_errs_wide_to_the_outermost_start_when_git_is_there(self):
        has_git = lambda p: p == Path("/work/repo")
        assert discover_root(Path("/work/repo"), has_git) == Path("/work/repo")

    def test_returns_none_without_any_git_ancestor(self):
        assert discover_root(Path("/work/elsewhere"), lambda p: False) is None


class TestRequireRoot:
    def test_explicit_root_must_exist(self):
        with pytest.raises(StructuredFailure) as failure:
            require_root(
                "/no/such/dir",
                Path("/work"),
                has_git=lambda p: False,
                is_directory=lambda p: False,
            )
        assert failure.value.kind == "root-not-found"

    def test_no_git_and_no_explicit_root_demands_one(self):
        with pytest.raises(StructuredFailure) as failure:
            require_root(
                None,
                Path("/work"),
                has_git=lambda p: False,
                is_directory=lambda p: True,
            )
        assert failure.value.kind == "root-required"
