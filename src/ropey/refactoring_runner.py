"""Refactoring Runner: executes one Refactoring under the transaction model.

Owns the serial-execution lock (the per-root Project's consistency
boundary — rope Projects are not thread-safe), the Dry Run / Live Run
``apply`` flag, and the shared call skeleton every tool goes through:

    lock -> resolve root -> fresh Project -> translate Location ->
    build ChangeSet -> report Blast Radius -> apply (Live Run only)

rope types flow freely here (ADR 0004) but never cross into tool inputs
or outputs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from rope.base import evaluate as rope_evaluate
from rope.base.change import Change, ChangeSet
from rope.base.project import Project
from rope.refactor.change_signature import (
    ArgumentAdder,
    ArgumentRemover,
    ArgumentReorderer,
    ChangeSignature,
)
from rope.refactor.extract import ExtractMethod, ExtractVariable
from rope.refactor.importutils import ImportOrganizer
from rope.refactor.inline import create_inline
from rope.refactor import occurrences as rope_occurrences
from rope.refactor.encapsulate_field import EncapsulateField
from rope.refactor.introduce_factory import IntroduceFactory
from rope.refactor.introduce_parameter import IntroduceParameter
from rope.refactor.localtofield import LocalToField
from rope.refactor.method_object import MethodObject
from rope.refactor.move import MoveMethod, create_move
from rope.refactor.rename import Rename
from rope.refactor.topackage import ModuleToPackage
from rope.refactor.usefunction import UseFunction

from .blast_radius_reporter import report
from .engine_session import engine_session
from .location_translator import (
    check_expected_symbol,
    offset_to_position,
    position_to_offset,
    range_to_offsets,
)
from .model import (
    FailureKind,
    Position,
    Range,
    RefactoringReport,
    StructuredFailure,
    UncertainOccurrence,
)
from .operability import CallMetrics, Stopwatch, observed
from .project_provider import ProjectProvider


class UncertainOccurrenceCollector:
    """Collects rope's unsure occurrences as flagged Locations.

    Wired as the ``unsure`` callback: returning False keeps every uncertain
    occurrence out of the Change Set (never silently included) while the
    collection surfaces each one in the result (never silently dropped).
    """

    def __init__(self):
        self.occurrences: list[UncertainOccurrence] = []

    def __call__(self, occurrence) -> bool:
        start, _ = occurrence.get_word_range()
        text = occurrence.resource.read()
        position = offset_to_position(text, start)
        snippet = text.split("\n")[position.line].strip()
        self.occurrences.append(
            UncertainOccurrence(
                path=occurrence.resource.path,
                position=position,
                snippet=snippet,
            )
        )
        return False


class RefactoringRunner:
    """Runs each Refactoring of the catalogue against a fresh, scoped Project."""

    def __init__(
        self, provider: ProjectProvider, lock: threading.Lock | None = None
    ):
        self._provider = provider
        self._lock = lock if lock is not None else threading.Lock()

    # -- the shared call skeleton -------------------------------------------

    def _execute(
        self,
        *,
        tool: str,
        file: str | None,
        root: str | None,
        apply: bool,
        build: Callable[[Project, object, UncertainOccurrenceCollector], Change],
    ) -> RefactoringReport:
        metrics = CallMetrics(tool=tool)
        with observed(metrics):
            with engine_session(
                self._provider, self._lock, metrics, file=file, root=root
            ) as project:
                resource = (
                    self._provider.resource_for(project, file)
                    if file is not None
                    else None
                )
                collector = UncertainOccurrenceCollector()
                with Stopwatch() as refactoring:
                    changes = build(project, resource, collector)
                    blast_radius = report(changes)
                    if apply:
                        project.do(changes)
                metrics.refactoring_ms = refactoring.ms
            metrics.outcome = "applied" if apply else "dry"
            return RefactoringReport(
                applied=apply,
                blast_radius=blast_radius,
                uncertain_occurrences=tuple(collector.occurrences),
            )

    def _point_offset(
        self, resource, position: Position, expected_symbol: str | None
    ) -> int:
        text = resource.read()
        offset = position_to_offset(text, position)
        if expected_symbol is not None:
            check_expected_symbol(text, offset, expected_symbol)
        return offset

    @staticmethod
    def _surface_uncertain(project, name, pyname, collector) -> None:
        """Surface Uncertain Occurrences for engines without an unsure hook.

        rope only exposes ``unsure`` on rename's occurrence finder; for the
        other point Refactorings this dedicated pass finds the same unsure
        candidates so they are reported rather than silently left untouched
        (ADR 0003).
        """
        finder = rope_occurrences.create_finder(project, name, pyname, unsure=collector)
        for resource in project.get_python_files():
            for _ in finder.find_occurrences(resource):
                pass

    # -- the catalogue -------------------------------------------------------

    def rename(
        self,
        *,
        file: str,
        position: Position,
        new_name: str,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        in_docstrings_and_comments: bool = False,
        across_class_hierarchy: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = Rename(project, resource, offset)
            return refactoring.get_changes(
                new_name,
                docs=in_docstrings_and_comments,
                in_hierarchy=across_class_hierarchy,
                unsure=collector,
            )

        return self._execute(
            tool="rename", file=file, root=root, apply=apply, build=build
        )

    def move(
        self,
        *,
        file: str,
        position: Position | None,
        destination: str | None = None,
        destination_attribute: str | None = None,
        new_name: str | None = None,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = (
                self._point_offset(resource, position, expected_symbol)
                if position is not None
                else None
            )
            mover = create_move(project, resource, offset)
            if isinstance(mover, MoveMethod):
                if destination_attribute is None:
                    raise StructuredFailure(
                        FailureKind.INVALID_ARGUMENT,
                        "The Target is a method, so the move needs "
                        "destination_attribute: the name of the attribute on "
                        "self that holds the destination instance.",
                    )
                return mover.get_changes(destination_attribute, new_name)
            if destination_attribute is not None:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    "destination_attribute applies only when the Target is a "
                    "method; this Target moves between modules, so pass "
                    "destination (a module file or package directory).",
                )
            if new_name is not None:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    "new_name applies only to method moves; rename separately "
                    "after moving.",
                )
            if destination is None:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    "The move needs destination: the path of the destination "
                    "module file (for globals) or package directory (for "
                    "whole-module moves).",
                )
            dest_resource = self._provider.resource_for(project, destination)
            return mover.get_changes(dest_resource)

        return self._execute(
            tool="move", file=file, root=root, apply=apply, build=build
        )

    def extract_method(
        self,
        *,
        file: str,
        selection: Range,
        name: str,
        apply: bool,
        root: str | None = None,
        replace_similar: bool = False,
        to_global_scope: bool = False,
        method_kind: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            start, end = range_to_offsets(resource.read(), selection)
            refactoring = ExtractMethod(project, resource, start, end)
            return refactoring.get_changes(
                name,
                similar=replace_similar,
                global_=to_global_scope,
                kind=method_kind,
            )

        return self._execute(
            tool="extract_method", file=file, root=root, apply=apply, build=build
        )

    def extract_variable(
        self,
        *,
        file: str,
        selection: Range,
        name: str,
        apply: bool,
        root: str | None = None,
        replace_similar: bool = False,
        to_global_scope: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            start, end = range_to_offsets(resource.read(), selection)
            refactoring = ExtractVariable(project, resource, start, end)
            return refactoring.get_changes(
                name, similar=replace_similar, global_=to_global_scope
            )

        return self._execute(
            tool="extract_variable", file=file, root=root, apply=apply, build=build
        )

    def inline(
        self,
        *,
        file: str,
        position: Position,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        remove_definition: bool = True,
        only_current_occurrence: bool = False,
        in_docstrings_and_comments: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            inliner = create_inline(project, resource, offset)
            kind = inliner.get_kind()
            if kind == "parameter":
                if (
                    not remove_definition
                    or only_current_occurrence
                    or in_docstrings_and_comments
                ):
                    raise StructuredFailure(
                        FailureKind.INVALID_ARGUMENT,
                        "The Target is a parameter (its default is inlined "
                        "into call sites); remove_definition, "
                        "only_current_occurrence and "
                        "in_docstrings_and_comments do not apply to it.",
                    )
                return inliner.get_changes()
            if kind != "variable" and in_docstrings_and_comments:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    f"The Target is a {kind}; in_docstrings_and_comments "
                    "applies only to variable inlines.",
                )
            kwargs: dict[str, Any] = {
                "remove": remove_definition,
                "only_current": only_current_occurrence,
            }
            if kind == "variable":
                kwargs["docs"] = in_docstrings_and_comments
            changes = inliner.get_changes(**kwargs)
            self._surface_uncertain(project, inliner.name, inliner.pyname, collector)
            return changes

        return self._execute(
            tool="inline", file=file, root=root, apply=apply, build=build
        )

    def change_signature(
        self,
        *,
        file: str,
        position: Position,
        operations: list[dict[str, Any]],
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        across_class_hierarchy: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            signature = ChangeSignature(project, resource, offset)
            parameter_names = [name for name, _ in signature.get_args()]
            changers = _signature_changers(operations, parameter_names)
            changes = signature.get_changes(
                changers, in_hierarchy=across_class_hierarchy
            )
            self._surface_uncertain(
                project, signature.name, signature.pyname, collector
            )
            return changes

        return self._execute(
            tool="change_signature", file=file, root=root, apply=apply, build=build
        )

    def introduce_parameter(
        self,
        *,
        file: str,
        selection: Range,
        parameter_name: str,
        apply: bool,
        root: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            start, _ = range_to_offsets(resource.read(), selection)
            refactoring = IntroduceParameter(project, resource, start)
            return refactoring.get_changes(parameter_name)

        return self._execute(
            tool="introduce_parameter", file=file, root=root, apply=apply, build=build
        )

    def encapsulate_field(
        self,
        *,
        file: str,
        position: Position,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        getter_name: str | None = None,
        setter_name: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = EncapsulateField(project, resource, offset)
            changes = refactoring.get_changes(
                getter=getter_name, setter=setter_name
            )
            self._surface_uncertain(
                project, refactoring.name, refactoring.pyname, collector
            )
            return changes

        return self._execute(
            tool="encapsulate_field", file=file, root=root, apply=apply, build=build
        )

    def introduce_factory(
        self,
        *,
        file: str,
        position: Position,
        factory_name: str,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
        global_factory: bool = False,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = IntroduceFactory(project, resource, offset)
            return refactoring.get_changes(
                factory_name, global_factory=global_factory
            )

        return self._execute(
            tool="introduce_factory", file=file, root=root, apply=apply, build=build
        )

    def method_object(
        self,
        *,
        file: str,
        position: Position,
        class_name: str,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = MethodObject(project, resource, offset)
            return refactoring.get_changes(classname=class_name)

        return self._execute(
            tool="method_object", file=file, root=root, apply=apply, build=build
        )

    def local_to_field(
        self,
        *,
        file: str,
        position: Position,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = LocalToField(project, resource, offset)
            return refactoring.get_changes()

        return self._execute(
            tool="local_to_field", file=file, root=root, apply=apply, build=build
        )

    def use_function(
        self,
        *,
        file: str,
        position: Position,
        apply: bool,
        root: str | None = None,
        expected_symbol: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            offset = self._point_offset(resource, position, expected_symbol)
            refactoring = UseFunction(project, resource, offset)
            changes = refactoring.get_changes()
            pyname = rope_evaluate.eval_location(
                project.get_pymodule(resource), offset
            )
            self._surface_uncertain(
                project, refactoring.pyfunction.get_name(), pyname, collector
            )
            return changes

        return self._execute(
            tool="use_function", file=file, root=root, apply=apply, build=build
        )

    def module_to_package(
        self,
        *,
        file: str,
        apply: bool,
        root: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            return ModuleToPackage(project, resource).get_changes()

        return self._execute(
            tool="module_to_package", file=file, root=root, apply=apply, build=build
        )

    def organize_imports(
        self,
        *,
        file: str,
        mode: str = "organize",
        apply: bool,
        root: str | None = None,
    ) -> RefactoringReport:
        def build(project, resource, collector):
            organizer = ImportOrganizer(project)
            actions = {
                "organize": organizer.organize_imports,
                "expand_star_imports": organizer.expand_star_imports,
                "relatives_to_absolutes": organizer.relatives_to_absolutes,
                "froms_to_imports": organizer.froms_to_imports,
                "handle_long_imports": organizer.handle_long_imports,
            }
            if mode not in actions:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    f"Unknown organize_imports mode {mode!r}; choose one of "
                    f"{sorted(actions)}.",
                )
            changes = actions[mode](resource)
            if changes is None:
                return ChangeSet(f"No {mode} changes needed")
            return changes

        return self._execute(
            tool="organize_imports", file=file, root=root, apply=apply, build=build
        )


def _signature_changers(
    operations: list[dict[str, Any]], parameter_names: list[str]
):
    """Translate published add/remove/reorder operations into rope changers.

    ``simulated`` tracks the parameter list as each operation lands, so a
    later operation may name a parameter an earlier one introduced and
    indices always mean "position at that step".
    """
    if not operations:
        raise StructuredFailure(
            FailureKind.INVALID_ARGUMENT,
            "change_signature needs at least one operation "
            "(add / remove / reorder).",
        )
    simulated = list(parameter_names)
    changers = []
    for operation in operations:
        action = operation.get("action")
        if action == "add":
            name = operation.get("name")
            if not name:
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    "An add operation needs the new parameter's name.",
                )
            index = operation.get("index", len(simulated))
            if not 0 <= index <= len(simulated):
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    f"add index {index} is out of range for parameters "
                    f"{simulated}.",
                )
            changers.append(
                ArgumentAdder(
                    index, name, operation.get("default"), operation.get("value")
                )
            )
            simulated.insert(index, name)
        elif action == "remove":
            index = _resolve_parameter(operation, simulated, "remove")
            changers.append(ArgumentRemover(index))
            simulated.pop(index)
        elif action == "reorder":
            order = operation.get("order")
            if not isinstance(order, list) or sorted(
                _order_indices(order, simulated)
            ) != list(range(len(simulated))):
                raise StructuredFailure(
                    FailureKind.INVALID_ARGUMENT,
                    f"A reorder operation needs 'order': a permutation of all "
                    f"current parameters {simulated} (names or indices).",
                )
            indices = _order_indices(order, simulated)
            changers.append(ArgumentReorderer(indices))
            simulated = [simulated[i] for i in indices]
        else:
            raise StructuredFailure(
                FailureKind.INVALID_ARGUMENT,
                f"Unknown change_signature action {action!r}; use add, "
                "remove, or reorder.",
            )
    return changers


def _resolve_parameter(
    operation: dict[str, Any], simulated: list[str], action: str
) -> int:
    if "index" in operation:
        index = operation["index"]
        if not isinstance(index, int) or not 0 <= index < len(simulated):
            raise StructuredFailure(
                FailureKind.INVALID_ARGUMENT,
                f"{action} index {index!r} is out of range for parameters "
                f"{simulated}.",
            )
        return index
    name = operation.get("name")
    if name in simulated:
        return simulated.index(name)
    raise StructuredFailure(
        FailureKind.INVALID_ARGUMENT,
        f"{action} needs 'name' or 'index' identifying one of the current "
        f"parameters {simulated}; got {name!r}.",
    )


def _order_indices(order: list[Any], simulated: list[str]) -> list[int]:
    indices = []
    for item in order:
        if isinstance(item, int):
            indices.append(item)
        elif isinstance(item, str) and item in simulated:
            indices.append(simulated.index(item))
        else:
            raise StructuredFailure(
                FailureKind.INVALID_ARGUMENT,
                f"reorder entry {item!r} names no current parameter "
                f"{simulated}.",
            )
    return indices
