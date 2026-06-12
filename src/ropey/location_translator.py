"""Location Translator: LSP Position/Range <-> rope offset.

The Anti-Corruption Layer on the input side (ADR 0001). LSP `character`
counts UTF-16 code units; rope offsets index Python strings (code points).
Pure functions over source text; no I/O, no rope, no MCP.
"""

from __future__ import annotations

from .model import FailureKind, Position, Range, StructuredFailure


def _utf16_width(char: str) -> int:
    return 2 if ord(char) > 0xFFFF else 1


def position_to_offset(text: str, position: Position) -> int:
    """Translate an LSP Position to a code-point offset into ``text``.

    A ``character`` past the end of the line clamps to the line end (the LSP
    convention); a ``line`` past the end of the file is a Structured Failure.
    """
    if position.line < 0 or position.character < 0:
        raise StructuredFailure(
            FailureKind.POSITION_OUT_OF_RANGE,
            f"Position {position.line}:{position.character} is negative; "
            "Positions are 0-based and non-negative.",
        )
    lines = text.split("\n")
    if position.line >= len(lines):
        raise StructuredFailure(
            FailureKind.POSITION_OUT_OF_RANGE,
            f"Position line {position.line} is past the end of the file "
            f"({len(lines)} lines).",
        )
    offset = sum(len(line) + 1 for line in lines[: position.line])
    units = 0
    for index, char in enumerate(lines[position.line]):
        if units >= position.character:
            return offset + index
        units += _utf16_width(char)
    return offset + len(lines[position.line])


def offset_to_position(text: str, offset: int) -> Position:
    """Translate a code-point offset back into an LSP Position."""
    offset = max(0, min(offset, len(text)))
    line = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    character = sum(_utf16_width(char) for char in text[line_start:offset])
    return Position(line=line, character=character)


def range_to_offsets(text: str, selection: Range) -> tuple[int, int]:
    """Translate an LSP Range to a (start, end) code-point offset pair."""
    start = position_to_offset(text, selection.start)
    end = position_to_offset(text, selection.end)
    if end < start:
        raise StructuredFailure(
            FailureKind.INVALID_SELECTION,
            "Range end Position precedes its start Position.",
        )
    return start, end


def _is_identifier_char(char: str) -> bool:
    return char.isalnum() or char == "_"


def identifier_at(text: str, offset: int) -> str | None:
    """The identifier at ``offset``, or None when none is there.

    Accepts an offset on any character of the identifier or immediately
    after it (a cursor at a word end still names that word).
    """
    if offset < len(text) and _is_identifier_char(text[offset]):
        start = offset
    elif offset > 0 and _is_identifier_char(text[offset - 1]):
        start = offset - 1
    else:
        return None
    while start > 0 and _is_identifier_char(text[start - 1]):
        start -= 1
    end = start
    while end < len(text) and _is_identifier_char(text[end]):
        end += 1
    return text[start:end]


def check_expected_symbol(text: str, offset: int, expected: str) -> None:
    """The stale-Location guard: Expected Symbol vs what is actually there.

    A mismatch is a Structured Failure, never a transformation of whatever
    happens to be at the Position now (ADR 0001).
    """
    found = identifier_at(text, offset)
    if found != expected:
        actually = f"found {found!r}" if found else "found no identifier"
        raise StructuredFailure(
            FailureKind.EXPECTED_SYMBOL_MISMATCH,
            f"Expected Symbol {expected!r} is not at the given Position "
            f"({actually}). The file has likely changed since the Location "
            "was obtained; re-read or re-query the LSP and retry.",
        )
