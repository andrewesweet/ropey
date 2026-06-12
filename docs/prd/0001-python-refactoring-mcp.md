# PRD: ropey — Python Refactoring MCP

> Authoritative inputs: [`CONTEXT.md`](../../CONTEXT.md) (ubiquitous language) and [`docs/adr/0001`](../adr/0001-lsp-coordinates-as-input-language.md), [`0002`](../adr/0002-cached-project-with-self-validating-freshness.md), [`0003`](../adr/0003-report-uncertain-occurrences.md). This PRD uses the glossary terms (Refactoring, Target, Location, Position, Range, Search Scope, Freshness, Blast Radius, Change Kind, Dry Run / Live Run, Uncertain Occurrence, Structured Failure) without restating them — see `CONTEXT.md`.

## Problem Statement

The coding agent (Claude in Claude Code / OpenCode) can read and navigate Python well — it runs Astral's **ty** as an LSP for symbol lookup, go-to-definition, and find-references. What it lacks is a safe way to *change* Python structurally. Today, when the agent needs to rename a symbol used across thirty files, move a function to another module and fix every import, extract a block into a helper, or change a function's signature and update all call sites, it does this by hand with text edits. That is slow, and worse, it is silently unreliable: the agent cannot be sure it found every reference, cannot prove a textual match is the *same* binding, and routinely leaves behind broken or half-renamed code. The very operations that most need cross-file, binding-aware precision are the ones a text editor is worst at.

The mature open-source library that does this correctly — [rope](https://github.com/python-rope/rope) — exists, but it has no agent-facing interface. Its API speaks in byte offsets and `Project` objects, not in the LSP coordinates the agent already holds.

## Solution

A Model Context Protocol (MCP) server that exposes rope's **refactoring** catalogue as tools the agent can call. The agent points at code using the exact LSP coordinates ty already returns; the server performs the behaviour-preserving transformation across the whole project and reports precisely what changed.

The capability is deliberately scoped to **manipulation**. Navigation stays with ty — the server never duplicates symbol lookup. The division of labour is: **ty finds and reads; ropey changes.**

Every tool shares one foundation (targeting, transaction model, output contract, project/freshness handling, and the uncertainty/failure contract). On top of that foundation, the refactoring catalogue is delivered in a fixed priority order across phases. This PRD specifies the foundation once and then the phased rollout. **Restructure** (rope's pattern→goal rewrite mini-language) is explicitly *not* covered here — it is a sub-DSL that warrants its own design pass and will be a separate follow-up PRD.

The audience for this PRD is the implementation agent. It specifies **what** the capability does for its user (the coding agent) and the constraints it must honour. It deliberately does **not** dictate tool shape, naming, signatures, result-field names, server transport, or runtime — those are the implementer's to decide (see Out of Scope).

## User Stories

**Targeting and the ty division of labour**

1. As a coding agent, I want to address a Refactoring's Target with the same `line`/`character` Position my LSP (ty) just returned, so that I don't have to learn or compute a new addressing scheme.
2. As a coding agent, I want point Refactorings to take a Position and selection Refactorings to take a Range, so that the input mirrors exactly what an editor selection or a go-to result gives me.
3. As a coding agent, I never want to see or compute a byte offset, so that rope's internal addressing never leaks into my reasoning.
4. As a coding agent, I want refactoring of non-ASCII source to target the correct character, so that emoji, accents, and CJK identifiers don't shift my edits by a column.
5. As a coding agent, I want each tool's description to tell me to use my LSP for finding and reading and this tool only for changing, so that I route navigation and manipulation to the right place.

**Transaction model: Dry Run and Live Run**

6. As a coding agent, I want every Refactoring tool to accept an `apply` flag, so that I can preview before committing with the same call I'd use to apply.
7. As a coding agent, I want a Dry Run to compute and report the full consequence while writing nothing to disk, so that I can assess a risky change before making it.
8. As a coding agent, I want a Live Run to apply the change atomically, so that the project is never left in a half-transformed state.
9. As a coding agent, I want a Dry Run and a Live Run to report identical detail, so that what I previewed is exactly what I get.

**Blast Radius: knowing what changed**

10. As a coding agent, I want every result to enumerate every affected resource, so that I always understand the full blast radius of my action.
11. As a coding agent, I want each affected resource tagged with its Change Kind (modified, created, moved, deleted), so that I can tell an edit from a new file from a rename.
12. As a coding agent, I want a moved/renamed resource to report its old path alongside the new, so that I can follow the relocation.
13. As a coding agent, I want a short description per affected resource rather than full file contents, so that the result stays token-cheap.
14. As a coding agent, I want to run `git diff` after a Live Run for exact text when I need it, so that the tool doesn't have to carry diffs I usually don't read.
15. As a coding agent, I want a Refactoring that creates a file (e.g. extract to a new module) or converts a module to a package to surface those resources in the Blast Radius, so that creations and structural changes are as visible as edits.

**Search Scope and project handling**

16. As a coding agent, I want the server to discover the project root automatically by walking up to the `.git` root, so that I don't have to specify a root for an ordinary refactor.
17. As a coding agent, I want the Search Scope to err wide rather than narrow, so that a cross-file rename never silently misses references in a sibling package.
18. As a coding agent, I want to override the root for a monorepo or unusual layout, so that I can scope occurrence-finding when the default isn't right.
19. As a coding agent, I never want a `.ropeproject/` folder (or any cache artifact) to appear in the repository, so that the tool leaves no footprint I have to gitignore or clean up.
20. As a repository owner, I want a typo'd or non-existent root to be rejected rather than silently created as a new directory, so that a mistake doesn't litter my filesystem.

**Freshness**

21. As a coding agent, I want the server to re-establish Freshness before every Refactoring, so that edits I (or anyone) made since the last call are reflected.
22. As a coding agent, I want Freshness to be source-agnostic — catching my own edits, the human's edits in another editor, `git checkout`, and formatter-on-save alike — so that no out-of-band change ever produces a stale-cache result.
23. As a coding agent, I want correctness to never depend on the host telling the server about edits, so that the tool is reliable regardless of how a file changed.

**Uncertainty and failure**

24. As a coding agent, I want a Refactoring to apply only the occurrences rope is certain about, so that I never get a wrong edit at a location that merely looked like a match.
25. As a coding agent, I want every Uncertain Occurrence surfaced in the result as a flagged Location, so that I can adjudicate the dynamically-typed cases myself using ty and my reading of the code.
26. As a coding agent, I never want an uncertain match silently included or silently dropped, so that the result is the whole truth about what was and wasn't touched.
27. As a coding agent, when a Refactoring cannot proceed I want a Structured Failure stating the failed precondition, so that I can adapt instead of parsing a stack trace.
28. As a coding agent, I never want the server to crash or return a bare traceback on a refused refactoring, so that one bad call doesn't derail my session.

**Tool descriptions optimised for Claude**

29. As a coding agent, I want each tool's description written to Anthropic's prompt-engineering guidance, so that I reliably understand when and how to use it.
30. As a coding agent, I want description trigger-language calibrated (not forceful "CRITICAL/MUST" phrasing), so that I neither over- nor under-trigger the tool.

**Phase 1 (v1) — Tier 1 refactorings**

31. As a coding agent, I want to **rename** a symbol and have every certain reference across the project updated, so that I can rename safely without a manual find-and-replace.
32. As a coding agent, I want rename to optionally update occurrences in docstrings and comments, so that a rename can be thorough when I ask it to be.
33. As a coding agent, I want rename to optionally apply across a class hierarchy, so that renaming an overridden method updates the whole hierarchy.
34. As a coding agent, I want to **move** a global function, class, or variable to another module with imports updated automatically, so that I can reorganise code without breaking references.
35. As a coding agent, I want to **move** a method to another class, so that I can relocate behaviour where it belongs.
36. As a coding agent, I want to **move** a whole module (addressing it without a Position) into a package, so that I can restructure packages safely.
37. As a coding agent, I want to **extract a method** from a selected block of statements, with parameters and returns inferred, so that I can factor out a helper without hand-tracing data flow.
38. As a coding agent, I want to **extract a variable** from a selected expression, so that I can name an intermediate value.
39. As a coding agent, I want to **inline** a method, variable, or parameter at a Position, with the server detecting which, so that I can collapse an indirection without telling rope its internal taxonomy.
40. As a coding agent, I want to **change a signature** — add, remove, reorder parameters, or change defaults — with every call site updated, so that an API change doesn't leave broken callers.
41. As a coding agent, I want to **organize imports** — sort, dedupe, expand star-imports, and convert relative to absolute — so that a module's imports are tidy and explicit.
42. As a coding agent, I want each Tier 1 Refactoring to expose its full useful option surface, so that I'm not limited to the happy-path variant.

**Phase 2 — Host hook accelerator**

43. As a coding agent, I want the Claude Code (and OpenCode) plugin to notify the server of host-routed edits so caches stay warm, so that repeated refactorings in a session are faster.
44. As a repository owner, I want the hook accelerator to be optional and degradable — never the correctness mechanism — so that disabling it only costs speed, never correctness.

**Phase 3 — Tier 2 refactorings**

45. As a coding agent, I want to **introduce a parameter** from a selected expression, so that I can parameterise a hard-coded value.
46. As a coding agent, I want to **encapsulate a field** behind a getter/setter, so that I can add access control to an attribute.

**Phase 4 — Tier 3 refactorings**

47. As a coding agent, I want to **introduce a factory** for a class, so that instantiation can be centralised.
48. As a coding agent, I want to convert a method into a **method object**, so that a complex method becomes a class I can decompose.
49. As a coding agent, I want to turn a **local variable into a field**, so that I can promote state to instance scope.
50. As a coding agent, I want to **use a function** wherever its body pattern recurs, so that duplicated logic can be replaced by a call.

**Cross-cutting**

51. As a coding agent, I want all of these capabilities delivered in the fixed priority order (Tier 1 → hooks → Tier 2 → Tier 3 → Restructure), so that the highest-value refactorings arrive first.
52. As a coding agent, I want git to be my primary means of reversal, so that undo uses the workflow I already rely on.

## Implementation Decisions

These decisions are fixed by the grilling session and the three ADRs. They constrain behaviour, **not** tool shape.

**Foundation**

- **Targeting (ADR 0001).** Every tool addresses a Target with LSP coordinates: a file plus a Position (`{line, character}`, both 0-based, `character` in UTF-16 code units) for point Refactorings, or a Range for selection Refactorings. The server is an Anti-Corruption Layer: it translates Location → rope byte offset internally and the offset never crosses the tool boundary. The implementer must correctly convert UTF-16 `character` units to rope's code-point offsets for non-ASCII source.
- **Transaction model.** Every Refactoring tool takes an `apply` flag. Dry Run (`apply: false`) computes the Change Set and writes nothing. Live Run (`apply: true`) applies atomically via rope `project.do`. Both modes return identical detail.
- **Blast Radius output.** Every result enumerates every affected resource with: path, Change Kind (`modified | created | moved | deleted`), `old_path` for moves, and a short description. Full modified content is never returned; the agent uses `git diff` after a Live Run. Creations and module→package conversions appear in the Blast Radius.
- **Project / cache / Freshness (ADR 0002).** One rope `Project` is kept alive in-process per root, constructed with `ropefolder=None` so no cache artifact is written into the repo. The Search Scope is the project root tree; the root is auto-discovered by walking up to the `.git` root (erring wide) and is overridable via an optional `root` parameter. Before every Refactoring the server re-establishes Freshness via rope's mtime-based, source-agnostic `validate()`. The implementer must guard against a typo'd root, because `Project(root)` creates the directory if absent. Reversal is git; rope's in-session undo is a non-relied-upon bonus.
- **Uncertainty & failure (ADR 0003).** rope's `unsure` callback is wired so that only certain occurrences are applied and every Uncertain Occurrence is enumerated in the result as a flagged Location — never silently included, never silently dropped. `RefactoringError` (and any refusal) maps to a Structured Failure stating the failed precondition; never a crash or bare traceback.
- **Tool-description quality.** Tool descriptions must be optimised for Claude per Anthropic's prompt-engineering guidance: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md . Deriving and applying that standard is an explicit implementer task; conformance is judged against that referenced guidance.

**Deep modules implied by the foundation** (the implementer may refine the boundaries; these are the natural seams):

- **Location Translator** — LSP Position/Range ⇄ rope offset, including UTF-16↔code-point conversion. Pure; narrow interface.
- **Project Provider / Freshness Manager** — root discovery, per-root in-process Project cache (`ropefolder=None`), mandatory `validate()` before each operation, typo'd-root guard.
- **Refactoring Runner** — executes a chosen rope refactoring under the `apply` flag; atomic `project.do` on Live Run.
- **Change Set Reporter** — maps rope `ChangeSet` → Blast Radius structure. Pure.
- **Uncertainty & Failure Mapper** — collects Uncertain Occurrences via rope's `unsure` hook; maps refusals → Structured Failure. Pure-ish.
- **Tool layer** — thin MCP adapter (registration + Claude-optimised descriptions). Shape, naming, and signatures are the implementer's discretion.
- *(Phase 2)* **Host Hook Bridge** — receives host edit signals and issues targeted `validate(file)`; optional and degradable.

**Catalogue dispatch facts** (informational, from the rope source; the implementer decides whether to surface combined or split tools): `rope.refactor.move.create_move(project, resource, offset=None)` auto-dispatches MoveGlobal / MoveMethod / MoveModule (offset omitted ⇒ whole-module move). `rope.refactor.inline.create_inline(project, resource, offset)` auto-dispatches InlineMethod / InlineVariable / InlineParameter. Extract has no factory: `ExtractMethod` and `ExtractVariable` are distinct.

**Phased rollout** (priority order fixed):

- **Phase 1 (v1):** Rename (with docstring/comment and whole-hierarchy options); Move (global / method / module); Extract Method; Extract Variable; Inline; Change Signature (add / remove / reorder params + default changes, updating all call sites); Organize Imports (sort, dedupe, expand star-imports, relative→absolute). Each exposes its full useful option surface.
- **Phase 2:** Claude Code Hooks + OpenCode equivalent as an optional, degradable cache-invalidation accelerator. Host `PostToolUse` (`Edit | Write | MultiEdit`) pings the server for a targeted `validate(file)`. **Must not** be a correctness mechanism — hooks see only host-routed edits; the foundation's mandatory self-validate remains the backstop whether or not a hook fired.
- **Phase 3 (Tier 2):** Introduce Parameter; Encapsulate Field.
- **Phase 4 (Tier 3, excluding Restructure):** Introduce Factory; Method Object; Local-to-Field; Use Function. (Change Occurrences is excluded — subsumed by Rename.)
- **Phase 5 — separate follow-up PRD:** Restructure (rope's pattern→goal mini-DSL). Forthcoming dedicated PRD; not specified here.

## Testing Decisions

A good test here asserts **externally observable behaviour at the tool boundary**, not internal structure — given a fixture repository and a tool call, assert the resulting files on disk, the reported Blast Radius, the surfaced Uncertain Occurrences, and the Structured Failures. Tests must not assert rope-internal types or private module wiring, so that the implementer stays free on tool shape.

**Mandated (confirmed with the requester): the Project Provider / Freshness Manager and the Refactoring Runner**, exercised by fixture-repository integration tests against *real* rope (not mocked). These tests carry the foundation's correctness contract and must cover at least:

- Root discovery walks up to the `.git` root; an explicit `root` override is honoured.
- No `.ropeproject/` (or any cache artifact) is written to the fixture repo after operations.
- An out-of-band edit (made by writing to the file directly, simulating another editor / git / formatter) between two calls is reflected in the second call's result — Freshness holds without any host notification.
- A Dry Run writes nothing to disk; a Live Run applies atomically; both report identical detail.
- A typo'd / non-existent root is rejected, not silently created.
- Representative Tier 1 refactorings run end-to-end on the fixtures, asserting the Blast Radius enumerates every affected file with correct Change Kinds (including a `created` file from extract-to-new-module and a `moved` resource with `old_path`).
- A dynamically-typed call site produces a reported Uncertain Occurrence rather than a silent edit; an invalid selection produces a Structured Failure with a reason.

**Implementer's discretion:** unit tests for the Location Translator (UTF-16↔code-point and boundary cases), the Change Set Reporter (kind mapping), and the Uncertainty & Failure Mapper are encouraged as fast pure-unit coverage but are not separately mandated, since their behaviour is also observable through the mandated integration tests.

**Prior art:** none in this repo yet (greenfield). rope's own `ropetest/` suite (e.g. `ropetest/refactor/movetest.py`) is a reference for constructing fixture projects and asserting refactoring outcomes.

## Out of Scope

- **Navigation, reading, and symbol lookup** — owned by ty (the LSP). This server never duplicates them.
- **Code formatting** — owned by the formatter (black / ruff).
- **Codegen-from-usage** — rope's `generate` (generate variable/function/class/module/package from an undefined name) is *not* behaviour-preserving and is excluded; scope is refactoring-only.
- **Restructure** — deferred to its own follow-up PRD.
- **Change Occurrences** — subsumed by Rename; not exposed.
- **Tool shape and packaging** — number of tools, names, signatures, whether rope APIs are combined or split, exact result-schema field names, MCP transport, runtime, and distribution are all the implementer's discretion.

## Further Notes

- The ubiquitous language is authoritative in [`CONTEXT.md`](../../CONTEXT.md); the three ADRs record the load-bearing decisions and their rejected alternatives. The implementer should read them before starting.
- A reference clone of rope exists locally at `/home/andre/code/github.com/python-rope/rope` for consulting the API and test suite.
- The asymmetric Search Scope risk is the single most important correctness property to preserve: under-scoping silently corrupts (missed references), whereas over-scoping only costs time (rope is binding-aware and won't touch unrelated same-named symbols). When in doubt, scope wider.
- A separate **Restructure** PRD will follow once this capability lands.
