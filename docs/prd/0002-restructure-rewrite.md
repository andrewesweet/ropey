# PRD: ropey — Restructure (Rewrite)

> Authoritative inputs: [`CONTEXT.md`](../../CONTEXT.md) (ubiquitous language) and the ADRs — foundation in [`0001`](../adr/0001-lsp-coordinates-as-input-language.md)–[`0004`](../adr/0004-rope-is-the-engine-not-a-swappable-detail.md), and this capability's [`0005`](../adr/0005-restructure-is-a-conformist-non-behaviour-preserving-sibling.md). This PRD is the **Phase 5 follow-up** promised by [PRD 0001](0001-python-refactoring-mcp.md). It **consumes the foundation by reference** — Search Scope, Freshness, Blast Radius, Change Kind, Dry Run / Live Run, Structured Failure, Uncertain Occurrence, the deep modules, the dependency directions — and does not restate it. It uses the new glossary terms (Rewrite, Pattern, Goal, Wildcard, Match Constraint, Match Site) without redefining them — see `CONTEXT.md`.

## Problem Statement

PRD 0001 delivers eleven behaviour-preserving Refactorings, each addressed by a Location. But a coding agent routinely needs a transformation none of them expresses: rewrite *every* site matching a structural shape into a different shape — migrate `${x}.get_attribute(${k})` to `${x}[${k}]`, replace a deprecated call form project-wide, collapse an idiom. This is not rename, move, extract, inline, or change-signature; it is a pattern→goal rewrite across the project. Today the agent does it by hand with text edits over many files, with the same silent unreliability PRD 0001 set out to remove — except worse, because these transformations are structural and easy to apply to the wrong sites.

rope already has the engine for this — `Restructure`, a pattern→goal mini-DSL with typed wildcards — but it sits outside PRD 0001's model in two load-bearing ways: it is **not addressed by a Location**, and it is **not behaviour-preserving**. PRD 0001 deliberately deferred it for exactly this reason. This PRD resolves how it joins the catalogue without diluting the guarantees the other eleven tools provide.

## Solution

One tool exposing rope's `Restructure` as a **Rewrite**: a sibling of Refactoring, not a kind of it (ADR 0005). The agent supplies a **Pattern** (match template with `${wildcard}` placeholders), a **Goal** (replacement template), optional per-Wildcard **Match Constraints**, and optional **imports** the Goal needs. The server rewrites every matching site across the Search Scope and reports both the file-level Blast Radius and the full **Match Site** enumeration.

The capability makes **no equivalence claim**: the agent asserts that Pattern and Goal are equivalent; the tool guarantees only that it rewrites exactly the matches it reports. The safety story therefore shifts from *tool-proven* to *agent-asserted-and-tool-surfaced* — every Match Site is enumerated so the agent can audit for over-matching, Dry Run plus `git diff` are how it verifies the equivalence the tool does not, and two guards stop the one tool that can mechanically emit broken code.

For this sibling, ropey is a **Conformist** to rope's *published* Restructure language (ADR 0005): Pattern, Goal, and Wildcard cross the tool boundary verbatim — the single deliberate relaxation of the "no rope vocabulary crosses" rule (ADR 0004), justified because these are rope's published, UI-facing vocabulary, not its internal model (Offset, ChangeSet, PyObject), which stays behind the ACL.

The audience is the implementation agent. This PRD specifies **what** the Rewrite does and the constraints it must honour, not tool shape, signatures, result-field names, or serialization (those remain the implementer's, per PRD 0001's Out of Scope, which carries over).

## User Stories

**Addressing a Rewrite (the Pattern-addressed input language)**

1. As a coding agent, I want to address a Rewrite with a Pattern and a Goal rather than a Location, so that I can express a structural transformation that has no single point or selection.
2. As a coding agent, I want `${wildcard}` placeholders in the Pattern, reusable in the Goal, so that I can carry matched sub-expressions into the replacement.
3. As a coding agent, I want to narrow a Wildcard with Match Constraints — `name`, `type`, `object`, `instance`, `exact`, `unsure` — so that I can stop a Pattern from firing on the wrong sites (the over-match control).
4. As a coding agent, I want a Match Constraint to reference my own symbols (`type=myapp.models.User`), so that I can pin a Pattern to a specific type without learning rope's internal model.
5. As a coding agent, I want to supply the imports my Goal introduces, so that a Goal naming a new symbol does not leave un-importable code.

**Knowing what fired — Match Sites and the over-match audit**

6. As a coding agent, I want every Match Site (the Location where the Pattern fired) enumerated in the result, on both Dry and Live runs, so that I can audit *where* the rewrite applied, not just which files changed.
7. As a coding agent, I want each Match Site tagged with its certainty (proven vs unsure), so that I can see which edits rest on a constraint rope could not prove.
8. As a coding agent, I want the file-level Blast Radius *and* the Match Site list, so that I can see both which resources changed and exactly where within them.
9. As a coding agent, I want a Match Site sited after a non-ASCII identifier to report a correct UTF-16 Range, so that I can feed it back to ty.

**Uncertainty — the `unsure` pre-adjudication knob**

10. As a coding agent, I want sites whose type constraint cannot be proven to be left un-rewritten by default but surfaced as uncertain Match Sites, so that a dynamically-typed site is never silently skipped.
11. As a coding agent, I want to set `unsure` on a Wildcard to include those unprovable sites, with them still flagged unsure in the result, so that I can pre-adjudicate inclusion and still audit what I included.

**Transaction model and verification**

12. As a coding agent, I want the same `apply` flag as every other tool — Dry Run previews and writes nothing, Live Run applies — so that Rewrite behaves like the rest of the catalogue.
13. As a coding agent, I want Dry Run and Live Run to report identical Match Sites and Blast Radius, so that what I previewed is what I get.
14. As a coding agent, I want to run `git diff` after a Live Run for exact text, so that the result stays token-cheap and I verify the asserted equivalence against real output.

**Failure and safety**

15. As a coding agent, I want a malformed Pattern/Goal (won't parse, no wildcards, or a Goal `${wildcard}` absent from the Pattern) to be a Structured Failure stating the failed precondition, so that I fix my input rather than apply garbage.
16. As a coding agent, I want a Rewrite that would produce unparsable Python to be a Structured Failure at Dry Run, naming the file and parse location, so that I never apply a syntax-breaking rewrite.
17. As a coding agent, I want zero matches to be a loud successful empty result ("0 Match Sites"), not a Structured Failure, so that I can tell "ran, matched nothing" from "refused to run".
18. As a coding agent, I want a gitignored file containing a textual Pattern match to be neither matched nor reported, so that the Search Scope contract holds for Rewrite as for every tool.

**Routing — when to reach for Rewrite**

19. As a coding agent, I want the tool description to tell me to prefer a dedicated behaviour-preserving refactoring whenever one fits, and use Rewrite only for structural transformations none covers, so that I do not reach for the unproven tool when a proven one would do.
20. As a coding agent, I want the description to state plainly that Rewrite is not behaviour-preserving and that I own the Pattern↔Goal equivalence, so that I treat its output as asserted, not guaranteed.

## Implementation Decisions

These are fixed by the grilling session and ADR 0005. They constrain behaviour, not tool shape. Everything in PRD 0001's Implementation Decisions (targeting translation, concurrency, project/cache/Freshness, the deep modules, dependency directions, operability, capacity envelope) **carries over unchanged** except where stated below.

- **Identity (ADR 0005).** Restructure enters as a **Rewrite** — a non-behaviour-preserving sibling of Refactoring. "Refactoring = behaviour-preserving" is left intact; the behaviour-changing semantics are quarantined under the Rewrite label.
- **Input language (ADR 0005).** A Rewrite is **Pattern-addressed**, not Location-addressed: Pattern + Goal + per-Wildcard Match Constraints + optional imports. Pattern, Goal, and Wildcard are adopted **verbatim from rope's published Restructure language** (Conformist). The sole coinage is **Match Constraint** (rope's generic `args` renamed). The full published constraint set — `name`, `type`, `object`, `instance`, `exact`, `unsure` — is exposed; *serialization* (raw `key=value` string vs structured object) is the implementer's discretion but must cover all six. A constraint may name a user symbol but never a rope-internal type — the Rewrite ACL seam.
- **Custom wildcards excluded.** rope's `wildcards` parameter (custom matcher *classes* programming against rope's internal AST) is Out of Scope — by ACL, boundary-testability, and YAGNI, not by trust. Match Constraint is the designated extension point: any future matcher is a new ropey-published key, testable at the boundary.
- **Match Site surfacing.** The result enumerates every Match Site (a Location — file + Range — where the Pattern fired), on both Dry and Live runs, beyond the file-level Blast Radius. Each carries a certainty (proven / unsure). No file contents are returned; `git diff` after a Live Run is the exact-text verifier. This generalizes the Uncertain Occurrence contract (ADR 0003) from uncertain matches to *all* matches: because nothing is tool-proven, every site is adjudicable.
- **`unsure` semantics.** Without `unsure`, a site whose type/object/instance constraint is unprovable is **not** rewritten but **is** surfaced as an uncertain Match Site. With `unsure` (per Wildcard), those sites **are** rewritten and **stay flagged** unsure. Nothing silently dropped, nothing silently applied as if certain.
- **imports, no inference.** rope's `imports` parameter is exposed; the server adds them to changed modules (rope dedupes existing ones). The server does **not** analyse the Goal to infer missing imports — that is ty's job. An omitted import yields broken code; the tool description states this responsibility.
- **Transaction model unchanged.** The uniform `apply` flag — no bespoke two-phase handshake. Dry Run and Live Run report identical Match Sites and Blast Radius. The description steers Dry-Run-first more firmly than for the safe tools, on the explicit grounds that nothing here is tool-proven.
- **Failure modes.** (a) Malformed Pattern/Goal (won't parse, no wildcards, Goal references an unknown `${wildcard}`) → Structured Failure stating the failed precondition. (b) **Syntax guard:** the server parse-checks each changed module against the computed Change Set (one `ast.parse` per touched module — stdlib, negligible cost, sited at the existing Change Set → Blast Radius seam); a Rewrite that would produce unparsable Python is a Structured Failure naming the **file and parse location** (site-level attribution is best-effort), caught at **Dry Run** so it is never applied. (c) Zero matches → a **loud successful empty result** ("0 Match Sites"), not a Structured Failure.
- **Reverse translation.** Match Sites report Ranges back to the agent, so Rewrite is the first tool to exercise offset → LSP UTF-16 Position/Range translation at scale (existing tools mostly consume Locations). This direction of the Location Translator becomes load-bearing and must be correct for non-ASCII source.
- **Search Scope.** A Rewrite runs across the standard Search Scope (root auto-discovery + gitignore + optional `root` override) — identical to every other tool. rope's per-call `resources` file-list is **not** exposed: over-match is controlled by Pattern and Match Constraints (semantic, precise), not by file scoping (coarse, redundant). Blast radius is checked via the Dry Run's Match Site preview, not trusted blindly.
- **Tool-description standard — third input category.** Rewrite is neither point nor selection; it is **Pattern-addressed**. The [tool-description standard](../tool-description-standard.md) and its CI test (`tests/test_tool_descriptions.py`) grow a third input category: Pattern-addressed tools are **exempt** from the 0-based/UTF-16 coordinate check (D5), and gain a new check that the description explains Pattern / Goal / Wildcard / Match Constraint and states non-behaviour-preservation. D8's forbidden-token test still holds (Pattern/Goal/Wildcard do not embed rope-internal tokens). The Rewrite description must, within D1–D8 and calibrated language, carry the routing rule (prefer a dedicated refactoring when one fits; Rewrite only when none does), the not-behaviour-preserving / agent-owns-equivalence statement, Dry-Run-first, constraints-as-over-match-control plus Match Site review, the no-import-inference responsibility, and clean-tree-before-Live-Run.

## Testing Decisions

Rewrite joins PRD 0001's mandated suite: fixture-repository integration tests against **real rope**, asserting externally observable behaviour at the tool boundary (files on disk, Blast Radius, Match Sites, Structured Failures) — never rope-internal types or private wiring. Each case is the executable form of a decision above:

- A Pattern rewrites exactly the matched sites; assert the Match Site enumeration (files + Ranges) and the file-level Blast Radius with correct Change Kinds.
- A Match Constraint narrows the match set: `${x}.save()` unconstrained matches a `dict` site and a `Model` site; `type=Model` drops the `dict` site.
- `unsure` both ways: an unprovable-type site is not rewritten by default but is surfaced as an uncertain Match Site; with `unsure` set it is rewritten and stays flagged.
- Zero matches → loud successful empty result ("0 Match Sites"), not a Structured Failure.
- A malformed Pattern/Goal → Structured Failure.
- A syntax-breaking Goal → Structured Failure at Dry Run, naming file + parse location; nothing written.
- `imports` added to changed modules for a Goal-introduced name; deduped when already present.
- Dry Run writes nothing; Live Run applies; both report identical Match Sites + Blast Radius.
- A gitignored file containing a textual Pattern match is neither matched nor reported.
- **Non-ASCII Match Site:** a match sited after an emoji/CJK identifier reports a correct UTF-16 Range — the mandated coverage of the newly load-bearing reverse translation.

**Implementer's discretion:** unit tests for the reverse (offset → UTF-16 Range) translation and the parse guard are encouraged as fast pure coverage but not separately mandated, since their behaviour is observable through the integration tests above.

## Out of Scope

PRD 0001's Out of Scope carries over (navigation, formatting, codegen-from-usage, Change Occurrences, tool shape and packaging). Additionally:

- **Custom wildcard classes** — rope's `wildcards` parameter; excluded (ACL / boundary-testability / YAGNI). Match Constraint is the extension point.
- **Per-call file-list scoping** — rope's `resources` parameter; not exposed. Scope is the standard Search Scope; precision is via constraints.
- **Import inference** — the server adds only the imports the agent supplies; detecting missing names is ty's job.
- **A two-phase apply handshake** — the uniform `apply` flag is unchanged; Dry-Run-first is steered by description, not enforced by mechanism.

## Further Notes

- ADR 0005 records the load-bearing decision and its rejected alternatives (widen "Refactoring"; force a Location anchor; ACL-wrap the DSL). The glossary additions (Rewrite, Pattern, Goal, Wildcard, Match Constraint, Match Site, and the Match Site certainty) are in `CONTEXT.md`; the context map records the one published-vs-internal ACL relaxation.
- On landing, update PRD 0001's deferral note (Phase 5 / Out of Scope) from "deferred to its own follow-up PRD" to "delivered in PRD 0002", and add Rewrite to the README catalogue (kept-current documentation contract, per `CLAUDE.md`).
- The single most important property to preserve: Rewrite is **agent-asserted, not tool-proven**. Every safety mechanism here — the Match Site enumeration, the certainty flag, the `unsure` knob, the parse guard, the conservative routing — exists because the equivalence claim belongs to the agent, and the tool's job is to make the full truth of what fired impossible to miss.
