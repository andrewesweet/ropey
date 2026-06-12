# Cached rope Project with self-validating freshness

Each refactoring runs against a rope `Project` scoped to a root directory, which defines the search universe for occurrence-finding. We keep one Project alive in the server process per root (warm parsed-module caches, faster repeat refactorings) but never persist rope's cache to disk (`ropefolder=None`), so nothing appears in the user's repo. The agent edits files out-of-band constantly, so before every refactoring the server makes rope's view match disk via rope's own mtime-based `validate()`, which is source-agnostic — it detects changes from host edits, another editor, git, or formatters alike. Correctness therefore never depends on the host being the only writer.

## Considered Options

- **Ephemeral Project per call** — recreate and discard each time. Bulletproof but re-parses every call and discards undo history.
- **Cached Project, trust-the-host invalidation** — fast, but silently stale whenever a non-host writer touches a file. Rejected.
- **Cached Project + mandatory mtime self-validate (chosen)** — warm caches and correctness for all writers; the self-validate is a stat-only tree pass.

## Consequences

- The project root defines search scope. Under-scoping silently misses references (corrupting); over-scoping only slows (rope is binding-aware). So the root errs wide: auto-discovered by walking up to the `.git` root, overridable via an optional `root` parameter.
- `Project(root)` creates the root dir if absent and would create `.ropeproject/` unless `ropefolder=None` — the implementer must pass `ropefolder=None` and guard against a typo'd root silently creating a directory.
- Reversal is git (primary). rope's in-session undo history exists as a bonus but is not relied upon and is lost on server restart.
- **Hooks are a fast-follow optimisation, not a correctness mechanism.** Claude Code `PostToolUse` (and OpenCode's equivalent) only observe host-routed edits, so they can drive *targeted* `validate(file)` to keep caches warm, but the mandatory self-validate remains the correctness backstop and must run regardless of whether a hook fired.
