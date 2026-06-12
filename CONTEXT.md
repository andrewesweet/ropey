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
The address of a Target, expressed in the LSP's vocabulary. Takes one of three forms: a file alone (whole-module Targets, e.g. moving a module), a file plus a Position (point Refactorings), or a file plus a Range (selection Refactorings). This is the **published input language** the agent uses; it is exactly what the ty LSP returns from navigation.
_Avoid_: offset, byte position, cursor (these are rope-internal or editor-internal).

**Position**:
A single point in a file: `{line, character}`, both 0-based, `character` in UTF-16 code units — the LSP convention. Used by point refactorings.

**Range**:
A start Position and an end Position delimiting a span of source. Used by selection refactorings (extract method/variable, introduce parameter).

**Offset** (internal only):
rope's native address — an integer character index into a file. Never exposed to the agent; the server translates Location → Offset at its boundary (an Anti-Corruption Layer).

**Project** (internal only):
The server's per-root stateful view of one Search Scope — the system's one aggregate. Identity is the root path; it never crosses the tool boundary. "Project" is reserved for this internal concept, which is why the published language avoids it elsewhere.

**Change Set** (internal only):
The complete set of resource changes a Refactoring would produce — rope's `ChangeSet`. Like Offset, it never crosses the tool boundary: the server translates it into the **Blast Radius**, which is the sole published report vocabulary.

**Change Kind**:
What happens to one affected resource: `modified` (contents edited), `created` (new file/package), `moved` (file renamed or relocated — carries `old_path`), `deleted`. Blast Radius enumeration must distinguish these, not just list edited files.

**Blast Radius**:
Every resource a Refactoring touches. The tool result always enumerates the full Blast Radius, on both a Dry Run and a Live Run, so the agent sees the complete consequence of its action.

**Dry Run / Live Run**:
A Dry Run (`apply: false`) computes the Change Set, reports it, and writes nothing. A Live Run (`apply: true`) applies the Change Set to disk — atomically with respect to other tool calls; crash mid-apply is recovered via git — and reports it. Both modes report the **same detail**: the full Blast Radius as a list of resources, each with its Change Kind and a short description. Full modified content is never returned; after a Live Run the agent uses `git diff` for exact text. Every Refactoring tool offers both modes via an `apply` flag.

**Search Scope**:
The set of files a Refactoring searches when finding occurrences — the project root tree **minus gitignored files**. Defines what a cross-file Refactoring can see. Errs wide (the repo / `.git` root) over tracked source: under-scoping silently misses references and corrupts; over-scoping tracked files only slows. Gitignored files (virtualenvs, build output, vendored/generated code) are excluded: they are not project source, and an edit there cannot be reverted by git. Overridable by the agent for monorepos. Falls back to rope's default exclusions when there is no git repo or no gitignore.
_Avoid_: project (reserved for the internal Project aggregate), workspace.

**Freshness**:
The invariant that rope's view of the source matches disk before every Refactoring. Guaranteed by the server itself (mtime-based, catches edits from any writer — agent, human, git, formatter), never delegated to the host. The basis on which a warm cache stays correct.

**Uncertain Occurrence**:
A candidate occurrence rope cannot statically prove refers to the Target, because Python is dynamically typed (e.g. `obj.save()` where `obj`'s type is unprovable). Never silently applied and never silently dropped — surfaced to the agent in the result as a flagged Location for it to adjudicate.
_Avoid_: ambiguous match, maybe-match.

**Structured Failure**:
The result when a Refactoring cannot proceed (invalid selection, name collision, unrefactorable Target). States the reason — the failed precondition — in machine-readable form using this glossary's vocabulary, never a crash or bare stack trace. rope's exception text may ride along as supplementary detail but is never the primary reason.

**Expected Symbol**:
An optional assertion the agent attaches to a point Refactoring: the identifier it believes sits at the Position. If the source has changed since the agent's LSP answer and a different identifier is there now, the Refactoring is a Structured Failure instead of a silent transformation of the wrong Target. The guard against a stale Location.

## Strategic classification

- **Core domain**: safe, behaviour-preserving manipulation with total transparency — the Blast Radius, Uncertain Occurrence, Freshness, and Structured Failure contracts, and the Search Scope asymmetry (under-scoping silently corrupts; over-scoping tracked files only slows). This is where the deep modelling and the testing rigour live.
- **Generic subdomains**: MCP transport, tool registration, packaging — kept thin; implementer's discretion.
- **Supporting (contingent)**: the host hook accelerator — an advisory cache-warming channel, never a correctness mechanism.

## Building blocks

- **Value objects** (immutable, defined by their attributes): Location, Position, Range, Expected Symbol, Blast Radius (and its entries with their Change Kinds), Uncertain Occurrence, Structured Failure.
- **The one aggregate**: the per-root Project — the server's stateful view of one Search Scope. Its identity is the root path; its consistency boundary is serial execution — Refactorings against it run one at a time, so no call ever observes another call's half-applied state.
- The domain is otherwise synchronous request/response by design — no domain events. The only event-like thing in the system is the Phase 4 host hook signal: an advisory integration event ("a host edit occurred at *path*") consumed solely for cache warmth, never for correctness.

## Context map

- **ty / LSP (upstream)**: ropey is a conformist to the LSP published language — Positions and Ranges are adopted verbatim as the input vocabulary.
- **rope (downstream, foreign model)**: full Anti-Corruption Layer in both directions. Offset (input side) and Change Set (result side) stop at the boundary; rope's `unsure` becomes the Uncertain Occurrence; rope's refusals become Structured Failures. **No rope-internal term ever crosses the tool boundary.**
- **Host (Claude Code / OpenCode)**: consumes the tools; in Phase 4 may additionally emit advisory edit events. Correctness never depends on the host.

## Relationships

- A **Refactoring** acts on a **Target**, which the agent identifies by a **Location**.
- A **Refactoring** searches its **Search Scope** for occurrences to update.
- **Freshness** is re-established before every **Refactoring**, so out-of-band edits never produce a stale-cache result.
- A **Location** is a file alone (whole-module Targets), a file plus a **Position** (point refactorings), or a file plus a **Range** (selection refactorings).
- An **Expected Symbol** may accompany a Position to guard against a stale Location.
- **Navigation** (ty/LSP) produces **Location**s; **Manipulation** (this server) consumes them. LSP is the shared language between the two.
- The server translates a **Location** into rope's **Offset** internally and rope's **Change Set** into the **Blast Radius**; neither internal term crosses the tool boundary.

## Example dialogue

> **Agent:** "ty's find-references put the `Config` class at line 12, character 6. I want to rename it to `Settings`."
> **Server:** "That's a point Refactoring (rename). Give me the Location — file plus that Position — and the new name. I'll translate the Position to rope's offset, run the rename across every file that references it, and hand you back what changed."
> **Agent:** "And to pull lines 40–47 out into a helper?"
> **Server:** "That's a selection Refactoring (extract method). It takes a Range, not a Position — the start and end of the block you highlighted."

## Flagged ambiguities

- "Location" deliberately means the LSP address (file + Position/Range), **not** rope's byte offset. The offset is internal and never named in a tool signature.
