"""Match Site Enumerator: every Location where the Pattern fired.

The Match Site half of the Rewrite's transparency contract (the Blast
Radius half stays with the Blast Radius Reporter). Because a Rewrite is
agent-asserted rather than tool-proven, every match is surfaced — on Dry
and Live runs alike — as a published Match Site in pre-apply coordinates,
exercising the offset -> LSP Range direction of the Location Translator.
"""

from __future__ import annotations

from rope.base.project import Project
from rope.refactor.similarfinder import SimilarFinder

from .location_translator import offset_to_position
from .model import MatchSite, Range

_SNIPPET_LIMIT = 160


def enumerate_match_sites(project: Project, pattern: str) -> tuple[MatchSite, ...]:
    """Every Match Site for ``pattern`` across the Search Scope, in file order."""
    sites: list[MatchSite] = []
    for resource in project.get_python_files():
        pymodule = project.get_pymodule(resource)
        text = pymodule.source_code
        for start, end in _match_regions(pymodule, pattern):
            sites.append(_site(resource.path, text, start, end))
    sites.sort(key=lambda site: (site.path, site.range.start.line))
    return tuple(sites)


def _match_regions(pymodule, pattern: str) -> list[tuple[int, int]]:
    finder = SimilarFinder(pymodule)
    return sorted(finder.get_match_regions(pattern, {}))


def _site(path: str, text: str, start: int, end: int) -> MatchSite:
    return MatchSite(
        path=path,
        range=Range(
            start=offset_to_position(text, start),
            end=offset_to_position(text, end),
        ),
        snippet=_snippet(text, start),
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
