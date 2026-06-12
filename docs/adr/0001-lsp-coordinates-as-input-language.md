# Use LSP coordinates as the input language for refactoring tools

The agent already runs ty as an LSP and gets `{line, character}` Positions and Ranges from navigation. We adopt those LSP coordinates verbatim as the address (`Location`) every refactoring tool takes, and the server translates them into rope's internal byte `offset` at its boundary (an Anti-Corruption Layer). The agent never sees an offset and learns no new addressing concept.

## Considered Options

- **LSP `line:character` (chosen)** — unambiguous, pipes ty's output straight in, thin translation layer.
- **Symbol name (+ disambiguator)** — most natural to phrase, but ambiguous under shadowing/overloads; the server would sometimes guess the wrong Target. Deferred; may be added later if usage shows the agent struggles to supply positions.
- **Raw rope offset** — rejected; no agent reasons in byte offsets.

## Consequences

- The server must convert LSP UTF-16 `character` units to rope's code-point offsets when reading each file. This conversion is the implementer's concern but must be correct for non-ASCII source.
- Point refactorings take a `Position`; selection refactorings (extract, introduce parameter) take a `Range`.
