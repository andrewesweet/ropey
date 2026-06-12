"""Scope Resolver: root discovery and gitignore-derived exclusions.

The highest-stakes correctness logic in the system (PRD): under-scoping
silently corrupts, over-scoping tracked files only slows, and gitignored
files must stay out because git cannot revert an edit there.

Pure policy over plain data: the caller supplies the ancestor listing and
gitignore contents; nothing here touches the filesystem.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from .model import FailureKind, StructuredFailure


def discover_root(start: Path, has_git: Callable[[Path], bool]) -> Path | None:
    """Walk up from ``start`` to the nearest directory containing ``.git``.

    Errs wide: the repository root, not the nearest package. Returns None
    when no ancestor has a ``.git`` — the caller must then demand an
    explicit root rather than guess (PRD story 20a).
    """
    current = start if start.is_absolute() else Path.cwd() / start
    for candidate in [current, *current.parents]:
        if has_git(candidate):
            return candidate
    return None


def require_root(
    explicit_root: str | None,
    start: Path,
    has_git: Callable[[Path], bool],
    is_directory: Callable[[Path], bool],
) -> Path:
    """Resolve the Search Scope root: explicit override or discovered .git root.

    A typo'd explicit root is rejected, never created; with no .git ancestor
    and no explicit root the call fails asking for one — the server never
    guesses scope.
    """
    if explicit_root is not None:
        root = Path(explicit_root)
        if not is_directory(root):
            raise StructuredFailure(
                FailureKind.ROOT_NOT_FOUND,
                f"The given root {explicit_root!r} does not exist or is not a "
                "directory. Nothing was created; check the path.",
            )
        return root.resolve()
    discovered = discover_root(start, has_git)
    if discovered is None:
        raise StructuredFailure(
            FailureKind.ROOT_REQUIRED,
            f"No .git root was found above {str(start)!r} and no explicit "
            "root was given. Pass a root parameter naming the Search Scope; "
            "the server never guesses one.",
        )
    return discovered


@dataclass(frozen=True)
class _ScopedSpec:
    """One .gitignore's patterns, anchored at the directory that holds it."""

    prefix: str  # POSIX-style path relative to root, "" for the root itself
    spec: GitIgnoreSpec


class ExclusionPolicy:
    """Decides whether a path (relative to the root) is outside the Search Scope.

    Built from a snapshot of every .gitignore in the tree, keyed by the
    directory holding it (POSIX-relative to the root; "" for the root).
    Nested files override outer ones; ``!`` negations are honoured within
    that precedence; ``.git`` itself is always excluded.
    """

    def __init__(self, gitignores: Mapping[str, str]):
        specs = []
        for prefix in sorted(gitignores, key=lambda p: p.count("/") if p else -1):
            lines = gitignores[prefix].splitlines()
            spec = GitIgnoreSpec.from_lines(lines)
            specs.append(_ScopedSpec(prefix=prefix, spec=spec))
        self._specs = specs

    def is_excluded(self, relative_path: str, is_directory: bool = False) -> bool:
        """True when the path or any of its ancestor directories is ignored."""
        if not relative_path:
            return False
        parts = relative_path.split("/")
        if ".git" in parts:
            return True
        for depth in range(1, len(parts)):
            if self._matches("/".join(parts[:depth]) + "/") is True:
                return True
        candidate = relative_path + "/" if is_directory else relative_path
        return self._matches(candidate) is True

    def _matches(self, relative_path: str) -> bool | None:
        decision: bool | None = None
        for scoped in self._specs:
            if scoped.prefix:
                if not relative_path.startswith(scoped.prefix + "/"):
                    continue
                candidate = relative_path[len(scoped.prefix) + 1 :]
            else:
                candidate = relative_path
            result = scoped.spec.check_file(candidate)
            if result.include is not None:
                decision = result.include
        return decision
