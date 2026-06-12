# Python Refactoring (MCP)

An MCP server that exposes the [rope](https://github.com/python-rope/rope) Python refactoring library as tools for a coding agent (Claude in Claude Code). It owns **manipulation** of Python source — behaviour-preserving transformations. **Navigation** (locating symbols, reading code) is owned by the ty LSP and is out of scope; this server consumes ty's output rather than duplicating it.

## Language

**Refactoring**:
A behaviour-preserving transformation of Python source that rope can perform (rename, move, extract, inline, change signature, …). Each exposed refactoring becomes one tool.
_Avoid_: edit, change, modification (too generic).

**Target**:
The code element a Refactoring acts on. Identified by a Location. Some Targets are named symbols (a function, class, variable); others are an arbitrary expression or statement block (for extract-style refactorings).
_Avoid_: subject, element, node.

**Location**:
The address of a Target, expressed in the LSP's vocabulary — a file plus a Position or a Range. This is the **published input language** the agent uses; it is exactly what the ty LSP returns from navigation.
_Avoid_: offset, byte position, cursor (these are rope-internal or editor-internal).

**Position**:
A single point in a file: `{line, character}`, both 0-based, `character` in UTF-16 code units — the LSP convention. Used by point refactorings.

**Range**:
A start Position and an end Position delimiting a span of source. Used by selection refactorings (extract method/variable, introduce parameter).

**Offset** (internal only):
rope's native address — an integer character index into a file. Never exposed to the agent; the server translates Location → Offset at its boundary (an Anti-Corruption Layer).

**Change Set**:
The complete set of resource changes a Refactoring would produce. rope's `ChangeSet`. Reported back to the agent as the tool's result. Each entry names an affected resource and its **Change Kind**.

**Change Kind**:
What happens to one affected resource: `modified` (contents edited), `created` (new file/package), `moved` (file renamed or relocated — carries `old_path`), `deleted`. Blast Radius enumeration must distinguish these, not just list edited files.

**Blast Radius**:
Every resource a Refactoring touches. The tool result always enumerates the full Blast Radius, on both a Dry Run and a Live Run, so the agent sees the complete consequence of its action.

**Dry Run / Live Run**:
A Dry Run (`apply: false`) computes the Change Set, reports it, and writes nothing. A Live Run (`apply: true`) applies the Change Set to disk atomically and reports it. Both modes report the **same detail**: the full Blast Radius as a list of resources, each with its Change Kind and a short description. Full modified content is never returned; after a Live Run the agent uses `git diff` for exact text. Every Refactoring tool offers both modes via an `apply` flag.

**Search Scope**:
The set of files a Refactoring searches when finding occurrences — the project root tree. Defines what a cross-file Refactoring can see. Errs wide (the repo / `.git` root): under-scoping silently misses references and corrupts; over-scoping only slows. Overridable by the agent for monorepos.
_Avoid_: project (rope-internal term), workspace.

**Freshness**:
The invariant that rope's view of the source matches disk before every Refactoring. Guaranteed by the server itself (mtime-based, catches edits from any writer — agent, human, git, formatter), never delegated to the host. The basis on which a warm cache stays correct.

**Uncertain Occurrence**:
A candidate occurrence rope cannot statically prove refers to the Target, because Python is dynamically typed (e.g. `obj.save()` where `obj`'s type is unprovable). Never silently applied and never silently dropped — surfaced to the agent in the result as a flagged Location for it to adjudicate.
_Avoid_: ambiguous match, maybe-match.

**Structured Failure**:
The result when a Refactoring cannot proceed (invalid selection, name collision, unrefactorable Target). States the reason — the failed precondition — in machine-readable form, never a crash or bare stack trace.

## Relationships

- A **Refactoring** acts on a **Target**, which the agent identifies by a **Location**.
- A **Refactoring** searches its **Search Scope** for occurrences to update.
- **Freshness** is re-established before every **Refactoring**, so out-of-band edits never produce a stale-cache result.
- A **Location** is a file plus either a **Position** (point refactorings) or a **Range** (selection refactorings).
- **Navigation** (ty/LSP) produces **Location**s; **Manipulation** (this server) consumes them. LSP is the shared language between the two.
- The server translates a **Location** into rope's **Offset** internally; the **Offset** never crosses the tool boundary.

## Example dialogue

> **Agent:** "ty's find-references put the `Config` class at line 12, character 6. I want to rename it to `Settings`."
> **Server:** "That's a point Refactoring (rename). Give me the Location — file plus that Position — and the new name. I'll translate the Position to rope's offset, run the rename across every file that references it, and hand you back what changed."
> **Agent:** "And to pull lines 40–47 out into a helper?"
> **Server:** "That's a selection Refactoring (extract method). It takes a Range, not a Position — the start and end of the block you highlighted."

## Flagged ambiguities

- "Location" deliberately means the LSP address (file + Position/Range), **not** rope's byte offset. The offset is internal and never named in a tool signature.
