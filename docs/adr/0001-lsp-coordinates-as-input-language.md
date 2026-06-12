# Use LSP coordinates as the input language for refactoring tools

The agent already runs ty as an LSP and gets `{line, character}` Positions and Ranges from navigation. We adopt those LSP coordinates verbatim as the address (`Location`) every refactoring tool takes, and the server translates them into rope's internal byte `offset` at its boundary (an Anti-Corruption Layer). The agent never sees an offset and learns no new addressing concept.

Location is the input language for every Refactoring. The one exception is the Rewrite sibling (Restructure), which is Pattern-addressed rather than Location-addressed — see [ADR 0005](0005-restructure-is-a-conformist-non-behaviour-preserving-sibling.md).

## Considered Options

- **LSP `line:character` (chosen)** — unambiguous, pipes ty's output straight in, thin translation layer.
- **Symbol name (+ disambiguator)** — most natural to phrase, but ambiguous under shadowing/overloads; the server would sometimes guess the wrong Target. Deferred; may be added later if usage shows the agent struggles to supply positions.
- **Raw rope offset** — rejected; no agent reasons in byte offsets.

## Consequences

- The server must convert LSP UTF-16 `character` units to rope's code-point offsets when reading each file. This conversion is the implementer's concern but must be correct for non-ASCII source.
- A Location takes one of three forms: file alone (whole-module Targets, e.g. move-module), file + `Position` (point refactorings), file + `Range` (selection refactorings — extract, introduce parameter).
- **Stale-Location guard.** A Position is only as fresh as the agent's last LSP answer; an intervening edit (formatter-on-save, human editor) can shift it so it addresses different code, and the server would faithfully refactor the wrong Target. Point refactorings therefore accept an optional **Expected Symbol** — the identifier the agent believes is at the Position. On mismatch the call is a Structured Failure, not a wrong transformation. Optional because the agent may legitimately call straight from a fresh read; the docs recommend supplying it whenever edits may have intervened.
- The same staleness applies to a `Range`, unguarded — accepted risk: a shifted selection produces visibly wrong output in the Dry Run's Blast Radius (an extract of the wrong lines is conspicuous) rather than a quiet cross-file rewrite, and git recovers a bad Live Run. A source-text check on Ranges may be added later if usage shows the need.
