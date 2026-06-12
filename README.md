# ropey

Safe, project-wide Python refactoring for coding agents. ropey is an
[MCP](https://modelcontextprotocol.io) server that exposes the
[rope](https://github.com/python-rope/rope) refactoring library as tools a
coding agent (Claude in Claude Code, OpenCode, or any MCP client) can call.

## Why

Coding agents read and navigate Python well. An LSP like Astral's ty
answers "where is this defined?" and "who references it?" precisely. What
agents lack is a safe way to *change* Python structurally. Renaming a symbol
used across thirty files by hand-editing text is slow and unreliable: the
agent can't be sure it found every reference, can't prove a textual match is
the same binding, and routinely leaves half-renamed code.

ropey closes that gap with one division of labour:

> ty finds and reads; ropey changes.

The agent points at code using the exact `line`/`character` coordinates its
LSP already returned, and ropey performs the behaviour-preserving
transformation across the whole project: rename, move, extract, inline,
change signature, organise imports, and so on. One sibling tool, `rewrite`,
takes a pattern→goal transformation for structural changes none of the
refactorings express. It is addressed by a code template rather than a
coordinate, and is explicitly *not* behaviour-preserving (see below).

## The safety contract

- **Dry Run by default.** Every tool takes an `apply` flag. With
  `apply=false` (the default) the full consequence is computed and reported
  but nothing is written. `apply=true` performs the same change for real.
  Both report identical detail.
- **The Blast Radius.** Every result enumerates every affected file with
  what happened to it: `modified`, `created`, `moved` (with its old path),
  or `deleted`. The list is never truncated and never carries file
  contents. After a live run, `git diff` shows the exact text.
- **Uncertain Occurrences.** Python is dynamically typed, so sometimes rope
  cannot prove that `obj.save()` refers to the method being renamed. ropey
  applies only the certain occurrences and reports every uncertain one as a
  flagged location for the agent to adjudicate. Nothing is silently included
  or silently dropped.
- **The Rewrite is agent-asserted, and says so.** `rewrite` is the one
  tool that makes no behaviour-preservation claim. The agent asserts that
  pattern and goal are equivalent, and the tool guarantees only that it
  rewrites exactly the matches it reports. In exchange it surfaces *every*
  Match Site (file + range, flagged `matched` or `unsure`) for the agent
  to audit, leaves unprovable sites un-rewritten unless explicitly opted
  in, and refuses any rewrite that would produce unparsable Python, in
  preview *and* apply mode alike.
- **Freshness is self-established.** Before every refactoring the server
  re-checks the source on disk, so edits from any writer are reflected,
  whether they came from the agent, a human editor, `git checkout`, or a
  formatter. Correctness never depends on the host announcing its edits.
- **git is the undo.** ropey writes no cache artifacts into your repo
  (no `.ropeproject/`), never edits gitignored files (git couldn't revert
  them), and recommends a clean working tree before applying so `git diff`
  / `git checkout` are always a complete reversal mechanism.
- **Failures are structured.** A refactoring that cannot proceed returns a
  machine-readable reason ("the selection crosses a scope boundary", "the
  file `broken.py` cannot be parsed") rather than a stack trace.

## Install

### Claude Code (plugin marketplace)

```
/plugin marketplace add andrewesweet/ropey
/plugin install ropey@ropey
```

The plugin bundles the MCP server config; tools appear after a restart.
Requires [uv](https://docs.astral.sh/uv/) on your PATH.

### OpenCode

Add to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ropey": {
      "type": "local",
      "command": [
        "uvx", "--from", "git+https://github.com/andrewesweet/ropey", "ropey"
      ],
      "enabled": true
    }
  }
}
```

### Any other MCP client

ropey is a standard stdio MCP server. Generic config:

```json
{
  "mcpServers": {
    "ropey": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/andrewesweet/ropey", "ropey"]
    }
  }
}
```

Or run it directly: `uvx --from git+https://github.com/andrewesweet/ropey ropey`

## The catalogue

| Tool | What it does |
| ---- | ------------ |
| `rename` | Rename a symbol everywhere, optionally in docstrings/comments and across a class hierarchy |
| `move` | Move a global, a method, or a whole module; imports updated project-wide |
| `module_to_package` | Convert a module file into a package |
| `extract_method` / `extract_variable` | Extract a selection into a helper or a named value |
| `inline` | Inline a method, variable, or parameter (kind auto-detected) |
| `change_signature` | Add / remove / reorder parameters with every call site updated |
| `organize_imports` | Sort, dedupe, expand star-imports, relative→absolute |
| `introduce_parameter` / `encapsulate_field` | Tier 2 |
| `introduce_factory` / `method_object` / `local_to_field` / `use_function` | Tier 3 |
| `rewrite` | Pattern→goal rewrite of every matching site (`${obj}.get_attribute(${key})` → `${obj}[${key}]`), with per-wildcard match constraints, certainty-flagged Match Sites, and a syntax guard. *Not* behaviour-preserving; the agent owns the equivalence |

Targets are addressed with LSP coordinates (0-based line/character, UTF-16
units), exactly what an LSP returns; byte offsets never appear. Point
refactorings accept an optional `expected_symbol` so a stale position fails
loudly instead of refactoring the wrong code. The exception is `rewrite`,
which is addressed by a *pattern* (Python source with `${wildcard}`
placeholders) instead of a coordinate, and reports its Match Sites back as
LSP ranges. ty finds and reads, ropey changes, and for the one tool that
cannot prove equivalence, ropey shows every site it touched so the agent
(and `git diff`) can verify.

## Development

```bash
uv sync
uv run pytest
```

Domain documentation lives in [`CONTEXT.md`](CONTEXT.md), the decision
records in [`docs/adr/`](docs/adr/), and the PRD in
[`docs/prd/`](docs/prd/). Operability notes and measured latency envelopes:
[`docs/operability.md`](docs/operability.md).
