"""Blast Radius Reporter: rope ChangeSet -> the published Blast Radius.

The Anti-Corruption Layer on the result side. The full enumeration is the
transparency contract: every affected resource, never truncated, never
carrying file contents (the agent uses ``git diff`` after a Live Run).
"""

from __future__ import annotations

from rope.base.change import (
    Change,
    ChangeContents,
    ChangeSet,
    CreateResource,
    MoveResource,
    RemoveResource,
)

from .model import BlastRadiusEntry, ChangeKind


def report(change_set: Change) -> tuple[BlastRadiusEntry, ...]:
    """Enumerate every affected resource with its Change Kind."""
    return tuple(_walk(change_set))


def _walk(change: Change):
    if isinstance(change, ChangeSet):
        for child in change.changes:
            yield from _walk(child)
    elif isinstance(change, ChangeContents):
        yield BlastRadiusEntry(
            path=change.resource.path,
            change_kind=ChangeKind.MODIFIED,
            description=f"Contents edited in {change.resource.path}",
        )
    elif isinstance(change, MoveResource):
        yield BlastRadiusEntry(
            path=change.new_resource.path,
            change_kind=ChangeKind.MOVED,
            description=(
                f"Moved {change.resource.path} to {change.new_resource.path}"
            ),
            old_path=change.resource.path,
        )
    elif isinstance(change, CreateResource):
        what = "folder" if change.resource.is_folder() else "file"
        yield BlastRadiusEntry(
            path=change.resource.path,
            change_kind=ChangeKind.CREATED,
            description=f"New {what} {change.resource.path}",
        )
    elif isinstance(change, RemoveResource):
        yield BlastRadiusEntry(
            path=change.resource.path,
            change_kind=ChangeKind.DELETED,
            description=f"Deleted {change.resource.path}",
        )
    else:
        for resource in change.get_changed_resources():
            yield BlastRadiusEntry(
                path=resource.path,
                change_kind=ChangeKind.MODIFIED,
                description=f"Changed {resource.path}",
            )
