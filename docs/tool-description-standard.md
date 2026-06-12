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
5. **"Tell Claude what to do instead of what not to do"** — balanced
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
  selections; file-only for whole-module Targets.
- **D6 Transaction model.** `apply` defaults to false (Dry Run
  preview, writes nothing); `apply=true` writes; both report the same
  detail.
- **D7 Result contract.** Mention Blast Radius / uncertain_occurrences
  / `git diff` where they guide the agent's next action.
- **D8 New-colleague test.** Self-contained, no engine internals, no
  glossary dependence beyond what the text itself explains.

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

| Check | Enforced by |
| ----- | ----------- |
| D1, D4, D8 | review against this file (judgement calls) |
| D2 no over-strong modals | test: forbidden tokens (CRITICAL, MUST, ALWAYS, NEVER, IMPORTANT) |
| D3 routing present | test: every description names the LSP-or-formatter route |
| D5 coordinate convention | test: point/selection tools mention "0-based" and "UTF-16" |
| D6 apply documented | test: every description mentions the Dry Run default and apply=true |
| D7 result contract | test: writing tools mention preview/Blast Radius terms |
| D8 no internals | test: forbidden tokens (rope, offset, ChangeSet, Project) |
