# Tool-description standard

Derived from Anthropic's prompting best practices
(<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md>),
as mandated by the PRD ("Tool-description quality"). Every ropey tool
description is written and audited against this checklist; future tools
must follow it.

## Derivation

The guidance points that bear on tool descriptions, and what each
implies here:

1. **"Be clear and direct… think of Claude as a brilliant but new
   employee."** → A description must be self-contained: what the tool
   does, the outcome, and the input conventions, with no internal
   jargon (no rope class names, no "offset").
2. **"Add context to improve performance… explain why such behavior is
   important. Claude is smart enough to generalize."** → Safety-relevant
   recommendations carry their motivation (e.g. *why* supply
   `expected_symbol`: the file may have changed since the LSP answer;
   *why* a clean tree: git is the reversal mechanism).
3. **"Where you might have said 'CRITICAL: You MUST use this tool
   when…', use more normal prompting like 'Use this tool when…'."**
   (Claude 4.5+ overtriggers on aggressive language.) → Trigger language
   is calibrated: plain "Use …" / "Prefer …" phrasing; no CRITICAL,
   MUST, ALWAYS, NEVER in trigger position.
4. **"Replace blanket defaults with targeted instructions… 'If in
   doubt, use [tool]' will cause overtriggering."** → Triggers name the
   concrete situation (renaming a symbol used across files), not a
   blanket "default to this tool".
5. **"Tell Claude what to do instead of what not to do"**, balanced
   against the routing need: each description states the positive
   route for out-of-scope work ("use your LSP to find and read;
   black/ruff to format") rather than bare prohibitions.
6. **Precise instruction following** → Parameter semantics are exact:
   0-based lines, UTF-16 character units, `apply` default false,
   defaults named in prose where behaviour-relevant.

## The checklist

Every tool description must:

- **D1 Outcome first.** Open with what the tool does and its
  project-wide outcome in one concrete sentence.
- **D2 Calibrated trigger.** State when to use it with plain "use
  when…" language; no over-strong modal phrasing, no blanket defaults.
- **D3 Routing, positively.** Say where neighbouring work belongs:
  LSP (ty) finds and reads; black/ruff format; ropey changes structure.
- **D4 Motivated safety.** Each safety recommendation states its
  reason (stale Locations, git reversal), so the model can generalise.
- **D5 Exact input language.** 0-based `line`/`character`, character
  in UTF-16 code units, "exactly as the LSP returns"; Range for
  selections; file-only for whole-module Targets. *Pattern-addressed
  tools are exempt* (see "The third input category" below): they have
  no input coordinates, so they state the Pattern/Goal language
  instead, and the coordinate convention applies to their *output*
  Ranges.
- **D6 Transaction model.** `apply` defaults to false (Dry Run
  preview, writes nothing); `apply=true` writes; both report the same
  detail.
- **D7 Result contract.** Mention Blast Radius / uncertain_occurrences
  / `git diff` where they guide the agent's next action.
- **D8 New-colleague test.** Self-contained, no engine internals, no
  glossary dependence beyond what the text itself explains.

## The third input category: Pattern-addressed tools

ADR 0005 admitted the Rewrite, which is neither a point nor a selection
tool: it is addressed by a Pattern and Goal, not a Location. For
these tools the checklist adapts:

- **D5 exemption.** No input coordinates exist, so the 0-based/UTF-16
  *input* check does not apply. The description instead explains the
  input language (Pattern, Goal, Wildcard, Match Constraint) by name
  and with a concrete example, and states the coordinate convention for
  the Match Site Ranges the tool *returns*.
- **New mandatory content.** The description must state, in calibrated
  language: that the tool is not behaviour-preserving and the agent
  owns the Pattern↔Goal equivalence; the routing rule (prefer a
  dedicated behaviour-preserving refactoring whenever one fits); the
  Dry-Run-first steer; Match Constraints as the over-match control plus
  Match Site review; the truncated-audit steer; the no-import-inference
  responsibility; and clean-tree-before-Live-Run.
- **D8 unchanged.** Pattern/Goal/Wildcard are rope's *published*
  vocabulary and cross verbatim (the Conformist seam); rope-internal
  tokens remain forbidden.

`tests/test_tool_descriptions.py` enforces the mechanical subset: the
four input-language terms and the non-behaviour-preservation statement
are present, and Pattern-addressed tools are excluded from the
point/selection coordinate check.

## Conformance

All fourteen registered tools (rename, move, module_to_package,
extract_method, extract_variable, inline, change_signature,
organize_imports, introduce_parameter, introduce_factory,
encapsulate_field, method_object, local_to_field, use_function) were
audited point-by-point against D1–D8 on 2026-06-12; the Tier 2/3 audit
found and fixed five judgement-level gaps (a missing routing sentence
on encapsulate_field; `expected_symbol` undocumented on
introduce_factory, method_object, local_to_field, use_function; an
unmotivated uncertain_occurrences mention on use_function).
`tests/test_tool_descriptions.py` enforces the mechanical subset
(calibrated language, apply documented, routing present, no internal
vocabulary) so regressions fail CI rather than review.

The fifteenth tool, `rewrite` (Pattern-addressed, PRD 0002), was audited
point-by-point against D1–D8 plus the third-category checks on
2026-06-12: outcome-first opening with a concrete Pattern/Goal example
(D1, D5-adapted); calibrated prefer-a-dedicated-refactoring routing
(D2); LSP routing for navigation and import inference (D3); motivated
safety throughout, covering why the agent owns equivalence, why clean
tree, and why unsure sites are excluded by default (D4); transaction
model and Dry Run default (D6); Blast Radius, Match Sites, certainty,
truncation steer, and `git diff` (D7); self-contained with no engine
internals (D8). All seven mandatory content items of the third category
are present and mechanically enforced where feasible.

| Check | Enforced by |
| ----- | ----------- |
| D1, D4, D8 | review against this file (judgement calls) |
| D2 no over-strong modals | test: forbidden tokens (CRITICAL, MUST, ALWAYS, NEVER, IMPORTANT) |
| D3 routing present | test: every description names the LSP-or-formatter route |
| D5 coordinate convention | test: point/selection tools mention "0-based" and "UTF-16" (Pattern-addressed tools exempt) |
| Pattern-addressed input language | test: Pattern, Goal, Wildcard, Match Constraint named; "not behaviour-preserving" stated |
| D6 apply documented | test: every description mentions the Dry Run default and apply=true |
| D7 result contract | test: writing tools mention preview/Blast Radius terms |
| D8 no internals | test: forbidden tokens (rope, offset, ChangeSet, Project) |
