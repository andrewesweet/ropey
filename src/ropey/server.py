"""Tool layer and composition root: the MCP adapter.

The only module that imports the MCP SDK. Inputs and outputs speak the
published vocabulary exclusively (Location, Blast Radius, Uncertain
Occurrence, Structured Failure) — no rope type and no offset crosses here.
"""

from __future__ import annotations

import threading
from typing import Any

from mcp.server.fastmcp import FastMCP

from .model import FailureKind, Position, Range, StructuredFailure
from .operability import configure_logging
from .project_provider import ProjectProvider
from .refactoring_runner import RefactoringRunner
from .rewrite_runner import RewriteRunner

SERVER_INSTRUCTIONS = """\
ropey changes Python code structure project-wide using LSP coordinates.
Use your LSP (ty) to find and read code; use ropey to change it. The
catalogue is behaviour-preserving refactorings plus one Rewrite (a
pattern->goal transformation whose equivalence you assert, not the tool).
Every tool previews with apply=false (Dry Run, writes nothing) and
applies with apply=true (Live Run); both report the same full Blast
Radius. Reversal is git — prefer a clean working tree before a Live Run,
and use `git diff` afterwards for exact text.
"""


def create_server() -> FastMCP:
    """Compose the server: project cache, shared engine lock, tool registration."""
    provider = ProjectProvider()
    # One lock across both runners: rope Projects are not thread-safe, so
    # the whole engine executes one call at a time.
    engine_lock = threading.Lock()
    runner = RefactoringRunner(provider, engine_lock)
    rewriter = RewriteRunner(provider, engine_lock)
    mcp = FastMCP("ropey", instructions=SERVER_INSTRUCTIONS)
    _register_rename_tool(mcp, runner)
    _register_catalogue(mcp, runner)
    _register_tier_2_and_3(mcp, runner)
    _register_rewrite(mcp, rewriter)
    return mcp


def _dispatch(action) -> dict[str, Any]:
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


def _register_rename_tool(mcp: FastMCP, runner: RefactoringRunner) -> None:
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
            "wrong code. Prefer a clean git working tree before applying, "
            "since git is the reversal mechanism; use `git diff` afterwards "
            "for exact text. Occurrences that cannot be proven to refer to "
            "this symbol are reported as uncertain_occurrences for you to "
            "adjudicate, never silently changed. Keep navigation and "
            "reading with your LSP, and formatting with black/ruff — this "
            "tool only changes code structure."
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
        return _dispatch(
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


def _register_catalogue(mcp: FastMCP, runner: RefactoringRunner) -> None:
    @mcp.tool(
        name="move",
        description=(
            "Move a Python symbol or module and update imports project-wide. "
            "Three targets, one tool: a global function/class/variable at a "
            "Position moves to another module (pass destination: that "
            "module's file path); a method at a Position moves to the class "
            "held by an attribute of self (pass destination_attribute, and "
            "optionally new_name); a whole module or package moves into a "
            "package when you omit line/character entirely (pass "
            "destination: the package directory). Coordinates are 0-based "
            "LSP line/character (UTF-16 units), exactly as your LSP "
            "returns them — locate the symbol with the LSP first. "
            "Defaults to a Dry Run preview; set apply=true to write. "
            "Prefer a clean git tree before applying, since git is the "
            "reversal mechanism. Moved resources report old_path; new "
            "files report created."
        ),
    )
    def move(
        file: str,
        destination: str | None = None,
        line: int | None = None,
        character: int | None = None,
        destination_attribute: str | None = None,
        new_name: str | None = None,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.move(
                file=file,
                position=_optional_position(line, character),
                destination=destination,
                destination_attribute=destination_attribute,
                new_name=new_name,
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
            )
        )

    @mcp.tool(
        name="extract_method",
        description=(
            "Extract a selected block of statements (or an expression) into "
            "a new method or function, with parameters and return values "
            "inferred from the data flow. Pass the file and the selection "
            "Range — start_line/start_character to end_line/end_character, "
            "0-based, character in UTF-16 units, exactly as an editor "
            "selection. The selection must be complete statements or one "
            "complete expression. Options: replace_similar replaces other "
            "occurrences of the same pattern; to_global_scope extracts to "
            "module level; method_kind makes a classmethod or staticmethod. "
            "Defaults to a Dry Run preview; set apply=true to write. Read "
            "the code with your LSP first; leave formatting to black/ruff."
        ),
    )
    def extract_method(
        file: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        name: str,
        apply: bool = False,
        root: str | None = None,
        replace_similar: bool = False,
        to_global_scope: bool = False,
        method_kind: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.extract_method(
                file=file,
                selection=Range(
                    Position(start_line, start_character),
                    Position(end_line, end_character),
                ),
                name=name,
                apply=apply,
                root=root,
                replace_similar=replace_similar,
                to_global_scope=to_global_scope,
                method_kind=method_kind,
            )
        )

    @mcp.tool(
        name="extract_variable",
        description=(
            "Extract a selected expression into a named variable, replacing "
            "the expression with the name. Pass the file and the selection "
            "Range (start_line/start_character to end_line/end_character, "
            "0-based, UTF-16 units) covering exactly one expression. "
            "replace_similar also substitutes other occurrences of the same "
            "expression; to_global_scope creates the variable at module "
            "level. Defaults to a Dry Run preview; set apply=true to "
            "write. Read the code with your LSP first; leave formatting "
            "to black/ruff."
        ),
    )
    def extract_variable(
        file: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        name: str,
        apply: bool = False,
        root: str | None = None,
        replace_similar: bool = False,
        to_global_scope: bool = False,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.extract_variable(
                file=file,
                selection=Range(
                    Position(start_line, start_character),
                    Position(end_line, end_character),
                ),
                name=name,
                apply=apply,
                root=root,
                replace_similar=replace_similar,
                to_global_scope=to_global_scope,
            )
        )

    @mcp.tool(
        name="inline",
        description=(
            "Inline the method, variable, or parameter at a Position — the "
            "server detects which kind, so just point at the name (0-based "
            "LSP line/character, UTF-16 units). Methods and variables: "
            "every certain use is replaced by the body or value; "
            "remove_definition=false keeps the definition; "
            "only_current_occurrence=true inlines just the occurrence at "
            "the Position. Parameters: the default value is written into "
            "call sites that omit it. Defaults to a Dry Run preview; set "
            "apply=true to write. Supply expected_symbol when edits may "
            "have intervened since your LSP answer, so a stale Position "
            "fails safely instead of inlining the wrong thing. Locate the "
            "definition with your LSP first; this tool only changes code."
        ),
    )
    def inline(
        file: str,
        line: int,
        character: int,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
        remove_definition: bool = True,
        only_current_occurrence: bool = False,
        in_docstrings_and_comments: bool = False,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.inline(
                file=file,
                position=Position(line, character),
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
                remove_definition=remove_definition,
                only_current_occurrence=only_current_occurrence,
                in_docstrings_and_comments=in_docstrings_and_comments,
            )
        )

    @mcp.tool(
        name="change_signature",
        description=(
            "Change a function or method signature — add, remove, or "
            "reorder parameters — updating every certain call site across "
            "the project. Point at the function name (0-based LSP "
            "line/character, UTF-16 units) and pass operations, a list "
            "applied in order: {action:'add', name, index?, default?, "
            "value?} (default is the parameter's default expression; value "
            "is what existing call sites should pass), {action:'remove', "
            "name or index}, {action:'reorder', order:[names or indices "
            "covering every parameter]}. For methods, parameter lists "
            "include self (index 0). across_class_hierarchy applies the "
            "change to matching overrides. Defaults to a Dry Run preview; "
            "set apply=true to write. Uncertain call sites are reported "
            "as uncertain_occurrences, never silently edited. Locate the "
            "function with your LSP first; this tool only changes code."
        ),
    )
    def change_signature(
        file: str,
        line: int,
        character: int,
        operations: list[dict[str, Any]],
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
        across_class_hierarchy: bool = False,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.change_signature(
                file=file,
                position=Position(line, character),
                operations=operations,
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
                across_class_hierarchy=across_class_hierarchy,
            )
        )

    @mcp.tool(
        name="module_to_package",
        description=(
            "Convert a Python module file into a package: creates a "
            "directory of the module's name and moves the module to its "
            "__init__.py, rewriting relative imports to absolute. Pass the "
            "module's file path alone; no Position needed. Defaults to a "
            "Dry Run preview (created and moved entries appear in the "
            "Blast Radius); set apply=true to write. Use your LSP for "
            "navigation and reading; this tool only restructures."
        ),
    )
    def module_to_package(
        file: str,
        apply: bool = False,
        root: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.module_to_package(file=file, apply=apply, root=root)
        )

    @mcp.tool(
        name="organize_imports",
        description=(
            "Tidy a module's import block structurally (not formatting — "
            "black/ruff own that). Pass the file alone; no Position. One "
            "mode per call: 'organize' (default) sorts, deduplicates, and "
            "drops unused imports; 'expand_star_imports' replaces `from m "
            "import *` with explicit names (follow with 'organize' to "
            "prune unused ones); 'relatives_to_absolutes' rewrites "
            "relative imports as absolute; 'froms_to_imports' converts "
            "from-imports to plain imports; 'handle_long_imports' shortens "
            "deep module paths. Defaults to a Dry Run preview; set "
            "apply=true to write. An empty blast_radius means the module "
            "already conforms."
        ),
    )
    def organize_imports(
        file: str,
        mode: str = "organize",
        apply: bool = False,
        root: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.organize_imports(
                file=file, mode=mode, apply=apply, root=root
            )
        )


def _register_tier_2_and_3(mcp: FastMCP, runner: RefactoringRunner) -> None:
    @mcp.tool(
        name="introduce_parameter",
        description=(
            "Turn a value used inside a function into a new parameter, "
            "with the original expression becoming the parameter's "
            "default. Select the expression — a name or attribute access "
            "such as a module constant or self.<attr> — with a Range "
            "(start_line/start_character to end_line/end_character, "
            "0-based, character in UTF-16 units) inside the function body "
            "and give the parameter a name. Defaults to a Dry Run preview; "
            "set apply=true to write. Read the code with your LSP first; "
            "this tool only changes code."
        ),
    )
    def introduce_parameter(
        file: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        parameter_name: str,
        apply: bool = False,
        root: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.introduce_parameter(
                file=file,
                selection=Range(
                    Position(start_line, start_character),
                    Position(end_line, end_character),
                ),
                parameter_name=parameter_name,
                apply=apply,
                root=root,
            )
        )

    @mcp.tool(
        name="encapsulate_field",
        description=(
            "Encapsulate a class attribute behind getter/setter methods, "
            "rewriting reads to the getter and writes to the setter across "
            "the project. Point at the attribute name (0-based LSP "
            "line/character, UTF-16 units), exactly as your LSP returns "
            "it. getter_name and setter_name override the default "
            "get_<field>/set_<field> names. Defaults to a Dry Run preview; "
            "set apply=true to write. Accesses that cannot be proven to be "
            "this attribute are reported as uncertain_occurrences, never "
            "silently rewritten. Supply expected_symbol when edits may "
            "have intervened since your LSP answer. Locate the attribute "
            "with your LSP first; this tool only changes code."
        ),
    )
    def encapsulate_field(
        file: str,
        line: int,
        character: int,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
        getter_name: str | None = None,
        setter_name: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.encapsulate_field(
                file=file,
                position=Position(line, character),
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
                getter_name=getter_name,
                setter_name=setter_name,
            )
        )

    @mcp.tool(
        name="introduce_factory",
        description=(
            "Introduce a factory for a class and route instantiations "
            "through it. Point at the class name (0-based LSP "
            "line/character, UTF-16 units). By default the factory is a "
            "static method named factory_name on the class; "
            "global_factory=true creates a module-level function instead. "
            "Existing constructor calls across the project are rewritten "
            "to the factory. Defaults to a Dry Run preview; set apply=true "
            "to write. Supply expected_symbol when edits may have "
            "intervened since your LSP answer, so a stale Position fails "
            "safely. Locate the class with your LSP first; this tool "
            "only changes code."
        ),
    )
    def introduce_factory(
        file: str,
        line: int,
        character: int,
        factory_name: str,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
        global_factory: bool = False,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.introduce_factory(
                file=file,
                position=Position(line, character),
                factory_name=factory_name,
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
                global_factory=global_factory,
            )
        )

    @mcp.tool(
        name="method_object",
        description=(
            "Convert a method into a method object: a new class whose "
            "__call__ holds the method body, with the original method "
            "delegating to it — a stepping stone for decomposing a complex "
            "method. Point at the method name (0-based LSP line/character, "
            "UTF-16 units) and name the new class. Defaults to a Dry Run "
            "preview; set apply=true to write. Supply expected_symbol "
            "when edits may have intervened since your LSP answer, so a "
            "stale Position fails safely. Read the method with your "
            "LSP first; this tool only changes code."
        ),
    )
    def method_object(
        file: str,
        line: int,
        character: int,
        class_name: str,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.method_object(
                file=file,
                position=Position(line, character),
                class_name=class_name,
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
            )
        )

    @mcp.tool(
        name="local_to_field",
        description=(
            "Promote a local variable inside a method to an instance "
            "field: the local becomes self.<name> everywhere in the "
            "class. Point at the local variable's name (0-based LSP "
            "line/character, UTF-16 units). Defaults to a Dry Run "
            "preview; set apply=true to write. Supply expected_symbol "
            "when edits may have intervened since your LSP answer, so a "
            "stale Position fails safely. Locate the variable with "
            "your LSP first; this tool only changes code."
        ),
    )
    def local_to_field(
        file: str,
        line: int,
        character: int,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.local_to_field(
                file=file,
                position=Position(line, character),
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
            )
        )

    @mcp.tool(
        name="use_function",
        description=(
            "Replace code that duplicates a function's body with calls to "
            "that function, across the whole project. Point at the name "
            "of a module-level function (0-based LSP line/character, "
            "UTF-16 units); statements matching its body pattern are "
            "rewritten into calls. Defaults to a Dry Run preview; set "
            "apply=true to write. Sites that cannot be proven to match "
            "are reported as uncertain_occurrences for you to adjudicate, "
            "never silently rewritten. Supply expected_symbol when edits "
            "may have intervened since your LSP answer, so a stale "
            "Position fails safely. Locate the function with your LSP "
            "first; this tool only changes code."
        ),
    )
    def use_function(
        file: str,
        line: int,
        character: int,
        apply: bool = False,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: runner.use_function(
                file=file,
                position=Position(line, character),
                apply=apply,
                root=root,
                expected_symbol=expected_symbol,
            )
        )


def _register_rewrite(mcp: FastMCP, rewriter: RewriteRunner) -> None:
    @mcp.tool(
        name="rewrite",
        description=(
            "Rewrite every site matching a structural Pattern into a Goal, "
            "project-wide — for transformations no dedicated refactoring "
            "expresses, such as migrating a deprecated call form "
            "(${obj}.get_attribute(${key}) -> ${obj}[${key}]) or collapsing "
            "an idiom. The Pattern is Python source with ${wildcard} "
            "placeholders; the Goal is the replacement template reusing "
            "those Wildcards. Prefer a dedicated behaviour-preserving tool "
            "(rename, inline, change_signature, move, use_function) "
            "whenever one fits; use rewrite only when none does, because a "
            "Rewrite is not behaviour-preserving: you assert that Pattern "
            "and Goal are equivalent, and the tool guarantees only that it "
            "rewrites exactly the Match Sites it reports. Control "
            "over-matching with per-Wildcard Match Constraints, e.g. "
            'constraints={"obj": {"type": "myapp.models.User"}}: name / '
            "type / object / instance narrow by a symbol's dotted path "
            "(one per Wildcard; instance also admits subclasses), and "
            "exact: true narrows to the Wildcard's literal name. Each Match "
            "Site reports its certainty: matched (constraints satisfied) or "
            "unsure (a constraint that cannot be established at that site, "
            "common in dynamically typed code). Unsure sites are surfaced "
            "but not rewritten, so nothing is silently skipped; add unsure: "
            "true to a Wildcard's constraints to rewrite them too — they "
            "stay flagged unsure in the result for you to audit. Defaults "
            "to a Dry Run that previews without writing; review every Match "
            "Site for over-matching before setting apply=true. Both modes "
            "report the "
            "file-level Blast Radius and every Match Site (file + Range in "
            "0-based UTF-16 LSP coordinates, against the pre-apply text — "
            "live targets for your LSP on a Dry Run, audit records after a "
            "Live Run). Start from a clean git tree, since git is the "
            "reversal mechanism, and run `git diff` after a Live Run to "
            "verify the equivalence you asserted. Pass root (the project "
            "directory) explicitly. Keep navigation and reading with your "
            "LSP; this tool only changes code."
        ),
    )
    def rewrite(
        pattern: str,
        goal: str,
        constraints: dict[str, dict[str, Any]] | None = None,
        apply: bool = False,
        root: str | None = None,
    ) -> dict[str, Any]:
        return _dispatch(
            lambda: rewriter.rewrite(
                pattern=pattern,
                goal=goal,
                constraints=constraints,
                apply=apply,
                root=root,
            )
        )


def _optional_position(line: int | None, character: int | None) -> Position | None:
    if line is None and character is None:
        return None
    if line is None or character is None:
        raise StructuredFailure(
            FailureKind.INVALID_ARGUMENT,
            "Pass line and character together (a point Location), or omit "
            "both (a whole-module Location).",
        )
    return Position(line, character)


def main() -> None:
    configure_logging()
    create_server().run()


if __name__ == "__main__":
    main()
