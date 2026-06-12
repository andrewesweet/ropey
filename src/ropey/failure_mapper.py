"""Uncertainty & Failure Mapper: rope refusals -> Structured Failures.

The Anti-Corruption Layer on the failure path (ADR 0003). The primary
``reason`` speaks the glossary vocabulary; rope's own message rides along
only as the supplementary ``detail`` field. No code path lets a bare
traceback cross the tool boundary.
"""

from __future__ import annotations

from contextlib import contextmanager

from rope.base.exceptions import (
    BadIdentifierError,
    ModuleDecodeError,
    ModuleSyntaxError,
    RefactoringError,
    ResourceNotFoundError,
    RopeError,
)

from .model import FailureKind, StructuredFailure


@contextmanager
def map_engine_failures():
    """Translate any engine refusal raised inside the block."""
    try:
        yield
    except StructuredFailure:
        raise
    except ModuleSyntaxError as error:
        raise StructuredFailure(
            FailureKind.UNPARSABLE_FILE,
            f"A file in the Search Scope cannot be parsed: {error.filename} "
            f"(line {error.lineno}). Fix or revert that file and retry; "
            "skipping it would silently drop its occurrences.",
            detail=str(error),
        ) from error
    except ModuleDecodeError as error:
        raise StructuredFailure(
            FailureKind.UNPARSABLE_FILE,
            f"A file in the Search Scope cannot be decoded: {error.filename}. "
            "Fix or revert that file and retry.",
            detail=str(error),
        ) from error
    except BadIdentifierError as error:
        raise StructuredFailure(
            FailureKind.TARGET_NOT_REFACTORABLE,
            "The Position does not address a resolvable Target; point at the "
            "name of a symbol (check the Location is fresh and 0-based).",
            detail=str(error),
        ) from error
    except ResourceNotFoundError as error:
        raise StructuredFailure(
            FailureKind.FILE_NOT_FOUND,
            "A resource named in the call does not exist in the Search Scope.",
            detail=str(error),
        ) from error
    except RefactoringError as error:
        raise StructuredFailure(
            FailureKind.TARGET_NOT_REFACTORABLE,
            "The Refactoring cannot proceed: the Target or selection fails a "
            "precondition of this Refactoring (see detail). Adjust the "
            "Location, the selection, or the options and retry.",
            detail=str(error),
        ) from error
    except RopeError as error:
        raise StructuredFailure(
            FailureKind.INTERNAL_ERROR,
            "The refactoring engine refused the operation.",
            detail=f"{type(error).__name__}: {error}",
        ) from error
