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
from rope.refactor.similarfinder import SimilarFinder

from .location_translator import offset_to_position
from .model import MatchCertainty, MatchSite, Range
from .rewrite_language import ConstraintArgs, narrowing_args, widening_args

_SNIPPET_LIMIT = 160

_Region = tuple[int, int]


def enumerate_match_sites(
    project: Project, pattern: str, args: ConstraintArgs
) -> tuple[MatchSite, ...]:
    """Every Match Site for ``pattern`` across the Search Scope, in file order."""
    narrowed = narrowing_args(args)
    widened = widening_args(args)
    sites: list[MatchSite] = []
    for resource in project.get_python_files():
        pymodule = project.get_pymodule(resource)
        text = pymodule.source_code
        candidates = _match_regions(pymodule, pattern, widened)
        certain = _reuse_or_scan(narrowed, widened, candidates, pymodule, pattern)
        included = _reuse_or_scan(args, narrowed, certain, pymodule, pattern)
        for region in candidates:
            sites.append(
                _site(
                    resource.path,
                    text,
                    region,
                    certain=region in certain,
                    included=region in included,
                )
            )
    sites.sort(key=lambda site: (site.path, site.range.start.line,
                                 site.range.start.character))
    return tuple(sites)


def _reuse_or_scan(
    args: ConstraintArgs,
    scanned_args: ConstraintArgs,
    scanned: set[_Region],
    pymodule,
    pattern: str,
) -> set[_Region]:
    if args == scanned_args:
        return scanned
    return _match_regions(pymodule, pattern, args)


def _match_regions(pymodule, pattern: str, args: ConstraintArgs) -> set[_Region]:
    # A fresh finder per reading: the finder caches matches by Pattern
    # text alone, so reusing one across constraint readings would return
    # the first reading's answer for every later one.
    finder = SimilarFinder(pymodule)
    return set(finder.get_match_regions(pattern, dict(args)))


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
