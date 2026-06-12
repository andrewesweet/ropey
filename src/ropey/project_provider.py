"""Project Provider: per-root cached rope Project with self-validating Freshness.

ADR 0002: one Project per root, kept warm in-process, never persisted
(``ropefolder=None``), LRU-bounded. Before every Refactoring the provider
re-establishes Freshness via rope's mtime-based ``validate()`` — correctness
never depends on the host announcing its edits.

This module is the humble I/O caller around the pure Scope Resolver: it
gathers the gitignore snapshot and applies the resolver's exclusion policy
by overriding rope's ``is_ignored`` filter point.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from rope.base.project import Project

from .model import FailureKind, StructuredFailure
from .scope_resolver import ExclusionPolicy, require_root

_CACHE_CAPACITY = 8


class _ScopedProject(Project):
    """A rope Project whose Search Scope honours gitignore exclusions."""

    def __init__(self, root: str, policy: ExclusionPolicy | None):
        self._exclusion_policy = policy
        super().__init__(root, ropefolder=None)

    def is_ignored(self, resource) -> bool:
        policy = getattr(self, "_exclusion_policy", None)
        if policy is None:
            # No git repo / no gitignore: rope's default exclusions apply.
            return super().is_ignored(resource)
        return policy.is_excluded(resource.path, resource.is_folder())


def _gather_gitignores(root: Path) -> dict[str, str]:
    """Snapshot every .gitignore in the tree, pruning ignored directories.

    Keys are POSIX paths of the holding directory relative to ``root``
    ("" for the root itself). Pruning uses the policy built so far: a
    .gitignore inside an already-ignored directory cannot matter.
    """
    gitignores: dict[str, str] = {}
    for current, dirnames, filenames in os.walk(root):
        relative = Path(current).relative_to(root).as_posix()
        relative = "" if relative == "." else relative
        if ".gitignore" in filenames:
            try:
                content = (Path(current) / ".gitignore").read_text(
                    encoding="utf-8", errors="replace"
                )
                gitignores[relative] = content
            except OSError:
                pass
        policy = ExclusionPolicy(gitignores)
        kept = []
        for name in sorted(dirnames):
            child = f"{relative}/{name}" if relative else name
            if name != ".git" and not policy.is_excluded(child, is_directory=True):
                kept.append(name)
        dirnames[:] = kept
    return gitignores


@dataclass
class _CacheEntry:
    project: Project
    gitignore_snapshot: dict[str, str] | None


class ProjectProvider:
    """Resolves the Search Scope root and serves a fresh, scoped Project."""

    def __init__(self, capacity: int = _CACHE_CAPACITY):
        self._capacity = capacity
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._cache_lock = threading.Lock()

    def resolve_root(self, file: str | None, explicit_root: str | None) -> Path:
        """The Search Scope root for a call: explicit override or .git walk-up."""
        if file is not None:
            start = Path(file).resolve().parent
        else:
            start = Path.cwd()
        return require_root(
            explicit_root,
            start,
            has_git=lambda p: (p / ".git").exists(),
            is_directory=lambda p: p.is_dir(),
        )

    def get_project(self, root: Path) -> Project:
        """A scoped Project for ``root`` with Freshness re-established.

        The gitignore snapshot is re-derived on every call; a changed
        snapshot rebuilds the Project so the file-list cache cannot serve
        a stale Search Scope.
        """
        key = str(root)
        has_git_repo = (root / ".git").exists()
        snapshot = _gather_gitignores(root) if has_git_repo else None
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is not None and entry.gitignore_snapshot != snapshot:
                entry.project.close()
                del self._cache[key]
                entry = None
            if entry is None:
                policy = ExclusionPolicy(snapshot) if snapshot is not None else None
                project = _ScopedProject(key, policy)
                entry = _CacheEntry(project=project, gitignore_snapshot=snapshot)
                self._cache[key] = entry
                while len(self._cache) > self._capacity:
                    _, evicted = self._cache.popitem(last=False)
                    evicted.project.close()
            self._cache.move_to_end(key)
        entry.project.validate(entry.project.root)
        return entry.project

    def resource_for(self, project: Project, file: str):
        """The rope resource for ``file``, which must lie inside the Search Scope."""
        absolute = Path(file).resolve()
        root = Path(project.address)
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError:
            raise StructuredFailure(
                FailureKind.FILE_OUT_OF_SCOPE,
                f"The file {file!r} lies outside the Search Scope root "
                f"{str(root)!r}. Pass a root that contains it.",
            ) from None
        if not absolute.exists():
            raise StructuredFailure(
                FailureKind.FILE_NOT_FOUND,
                f"The file {file!r} does not exist.",
            )
        return project.get_resource(relative)
