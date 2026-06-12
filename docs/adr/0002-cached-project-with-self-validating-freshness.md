# Cached rope Project with self-validating freshness

Each refactoring runs against a rope `Project` scoped to a root directory, which defines the search universe for occurrence-finding. We keep one Project alive in the server process per root (warm parsed-module caches, faster repeat refactorings) but never persist rope's cache to disk (`ropefolder=None`), so nothing appears in the user's repo. The agent edits files out-of-band constantly, so before every refactoring the server makes rope's view match disk via rope's own mtime-based `validate()`, which is source-agnostic: it detects changes from host edits, another editor, git, or formatters alike. Correctness therefore never depends on the host being the only writer.

## Considered Options

- **Ephemeral Project per call.** Recreate and discard each time. Always correct, but re-parses every call and discards undo history.
- **Cached Project, trust-the-host invalidation.** Fast, but silently stale whenever a non-host writer touches a file. Rejected.
- **Cached Project + mandatory mtime self-validate (chosen).** Warm caches and correctness for all writers; the self-validate is a stat-only tree pass.

## Consequences

- The project root defines search scope. Under-scoping silently misses references (corrupting); over-scoping *tracked* files only slows (rope is binding-aware). So the root errs wide: auto-discovered by walking up to the `.git` root, overridable via an optional `root` parameter.
- **Gitignored files are excluded from the search scope.** "Over-scoping only slows" is false for gitignored files: an edit to a gitignored file (odd venv name, `build/`, vendored code) cannot be reverted by git, breaking the reversal contract, and scanning large ignored trees is pure cost. rope's default `ignored_resources` covers only common names (`.venv`, `venv`, `.tox`, …); the server must derive exclusions from gitignore so the scope is exactly the tracked/un-ignored tree. It falls back to rope defaults when no git repo or gitignore exists.
- `Project(root)` creates the root dir if absent and would create `.ropeproject/` unless `ropefolder=None`. The implementer must pass `ropefolder=None` and guard against a typo'd root silently creating a directory.
- Reversal is git (primary). rope's in-session undo history exists as a bonus but is not relied upon and is lost on server restart.
- **Atomicity is per-call, not crash-proof.** A Live Run is atomic with respect to other tool calls (the serial-execution boundary), but rope's `project.do` writes files sequentially: process death mid-apply can leave a partial Change Set on disk. This is an accepted risk; recovery is git, which is also why Live Runs are best made against a clean working tree (tool descriptions should say so).
- **Freshness has a validate→apply window.** Freshness is established at call start, not held through apply; an out-of-band write landing inside a call's execution races it. This is an accepted risk: the window is milliseconds, and git reverts a bad outcome.
- **Cross-process instances are not coordinated.** Two hosts (e.g. two sessions) each spawn their own server against the same repo; the in-process lock does not serialise across them. This is an accepted risk for v1, with the same blast-radius-via-git recovery; an advisory file lock is an implementer option if it proves real.
- **The per-root Project cache is bounded.** Roots are few per session, but the cache must not grow without limit: evict least-recently-used beyond a small cap (order of 8 roots).
- **Hooks are a contingent later optimisation, not a correctness mechanism.** Deprioritised behind the full refactoring catalogue; build only if measured `validate()` latency justifies it. Claude Code `PostToolUse` (and OpenCode's equivalent) only observe host-routed edits, so they can drive *targeted* `validate(file)` to keep caches warm, but the mandatory self-validate remains the correctness backstop and must run regardless of whether a hook fired.
