"""Tool layer and composition root: the MCP adapter.

The only module that imports the MCP SDK. Inputs and outputs speak the
published vocabulary exclusively (Location, Blast Radius, Uncertain
Occurrence, Structured Failure) — no rope type and no offset crosses here.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .model import FailureKind, Position, StructuredFailure
from .project_provider import ProjectProvider
from .refactoring_runner import RefactoringRunner

SERVER_INSTRUCTIONS = """\
ropey performs behaviour-preserving Python refactorings project-wide using
LSP coordinates. Use your LSP (ty) to find and read code; use ropey to
change it. Every tool previews with apply=false (Dry Run, writes nothing)
and applies with apply=true (Live Run); both report the same full Blast
Radius. Reversal is git — prefer a clean working tree before a Live Run,
and use `git diff` afterwards for exact text.
"""


def create_server() -> FastMCP:
    """Compose the server: project cache, lock, and tool registration."""
    runner = RefactoringRunner(ProjectProvider())
    mcp = FastMCP("ropey", instructions=SERVER_INSTRUCTIONS)
    _register_tools(mcp, runner)
    return mcp


def _run(action) -> dict[str, Any]:
    """Run one tool call; every refusal becomes a Structured Failure dict."""
    try:
        return action().to_dict()
    except StructuredFailure as failure:
        return failure.to_dict()
    except Exception as error:  # never a bare traceback across the boundary
        return StructuredFailure(
            FailureKind.INTERNAL_ERROR,
            "The server hit an unexpected error while refactoring.",
            detail=f"{type(error).__name__}: {error}",
        ).to_dict()


def _register_tools(mcp: FastMCP, runner: RefactoringRunner) -> None:
    @mcp.tool(
        name="rename",
        description=(
            "Rename a Python symbol (function, class, method, variable, "
            "module-level name) and update every reference across the "
            "project — a binding-aware alternative to find-and-replace. "
            "Use your LSP to locate the symbol first; pass its file and "
            "0-based line/character Position (character in UTF-16 units, "
            "exactly as the LSP returns). Defaults to a Dry Run that "
            "previews the full Blast Radius without writing; set apply=true "
            "to write. Supply expected_symbol (the identifier you believe "
            "is at the Position) when edits may have happened since your "
            "LSP answer — a mismatch fails safely instead of renaming the "
            "wrong code. Prefer a clean git working tree before applying; "
            "use `git diff` afterwards for exact text. Occurrences rope "
            "cannot prove certain are reported as uncertain_occurrences "
            "for you to adjudicate, never silently changed. Not for "
            "navigation or formatting."
        ),
    )
    def rename(
        file: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
        in_docstrings_and_comments: bool = False,
        across_class_hierarchy: bool = False,
    ) -> dict[str, Any]:
        return _run(
            lambda: runner.rename(
                file=file,
                position=Position(line=line, character=character),
                new_name=new_name,
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
                in_docstrings_and_comments=in_docstrings_and_comments,
                across_class_hierarchy=across_class_hierarchy,
            )
        )


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
