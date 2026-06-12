"""Match Site Enumerator: every Location where the Pattern fired.

The Match Site half of the Rewrite's transparency contract (the Blast
Radius half stays with the Blast Radius Reporter). Because a Rewrite is
agent-asserted rather than tool-proven, every match is surfaced — on Dry
and Live runs alike — as a published Match Site in pre-apply coordinates,
exercising the offset -> LSP Range direction of the Location Translator.

Certainty needs the Pattern matched under more than one constraint
reading, so each module is scanned with up to three: the *narrowed* args
(``unsure`` stripped) establish which sites are certain; the *widened*
args (``unsure`` everywhere a symbol check could fail) enumerate every
candidate site; the agent's own args decide which sites the rewrite
includes. Readings that coincide share one scan.
"""

from __future__ import annotations

from rope.base.project import Project
from rope.refactor.similarfinder import ExpressionMatch, Match, SimilarFinder

from .location_translator import offset_to_position
from .model import MatchCertainty, MatchSite, Range
from .rewrite_language import ConstraintArgs, narrowing_args, widening_args

_SNIPPET_LIMIT = 160

_Region = tuple[int, int]


def enumerate_match_sites(
    project: Project, pattern: str, args: ConstraintArgs
) -> tuple[MatchSite, ...]:
    """Every Match Site for ``pattern`` across the Search Scope, in file order."""
    sites: list[MatchSite] = []
    for resource in project.get_python_files():
        pymodule = project.get_pymodule(resource)
        sites.extend(
            _module_sites(resource.path, pymodule, pattern, args)
        )
    sites.sort(
        key=lambda site: (
            site.path,
            site.range.start.line,
            site.range.start.character,
        )
    )
    return tuple(sites)


def _module_sites(
    path: str, pymodule, pattern: str, args: ConstraintArgs
) -> list[MatchSite]:
    scan = _ScanCache(pymodule, pattern)
    candidates = scan.matches(widening_args(args))
    certain = {match.get_region() for match in scan.matches(narrowing_args(args))}
    rewritten = _rewritten_regions(scan.matches(args))
    text = pymodule.source_code
    return [
        _site(
            path,
            text,
            match.get_region(),
            certain=match.get_region() in certain,
            included=match.get_region() in rewritten,
        )
        for match in candidates
    ]


class _ScanCache:
    """One matcher scan per distinct constraint reading of a module.

    A fresh finder per reading: the finder caches matches by Pattern text
    alone, so reusing one across readings would return the first reading's
    answer for every later one.
    """

    def __init__(self, pymodule, pattern: str):
        self._pymodule = pymodule
        self._pattern = pattern
        self._scans: list[tuple[ConstraintArgs, list[Match]]] = []

    def matches(self, args: ConstraintArgs) -> list[Match]:
        for scanned_args, matches in self._scans:
            if scanned_args == args:
                return matches
        finder = SimilarFinder(self._pymodule)
        matches = list(finder.get_matches(self._pattern, dict(args)))
        self._scans.append((dict(args), matches))
        return matches


def _rewritten_regions(matches: list[Match]) -> set[_Region]:
    """The matches the engine actually rewrites, mirroring its overlap rule:
    a statement match starting inside an earlier match is skipped (nested
    expression matches are substituted recursively, so they all apply)."""
    rewritten: set[_Region] = set()
    last_end = -1
    for match in matches:
        start, end = match.get_region()
        if start < last_end and not isinstance(match, ExpressionMatch):
            continue
        last_end = end
        rewritten.add((start, end))
    return rewritten


def _site(
    path: str, text: str, region: _Region, *, certain: bool, included: bool
) -> MatchSite:
    start, end = region
    return MatchSite(
        path=path,
        range=Range(
            start=offset_to_position(text, start),
            end=offset_to_position(text, end),
        ),
        snippet=_snippet(text, start),
        certainty=MatchCertainty.MATCHED if certain else MatchCertainty.UNSURE,
        included=included,
    )


def _snippet(text: str, start: int) -> str:
    """The source line holding the match start, trimmed — never file contents."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    if len(line) > _SNIPPET_LIMIT:
        return line[: _SNIPPET_LIMIT - 1] + "…"
    return line
