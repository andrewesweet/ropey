# rope is the engine, not a swappable detail

The server is built directly on rope: the Refactoring Runner calls rope's refactoring classes concretely, the Project Provider holds a rope `Project`, and rope's `unsure` callback and `project.do` are wired without an intermediating port. We deliberately do **not** define a "refactoring engine" port/interface that rope merely implements.

## Considered Options

- **Port over the engine** — an abstract refactoring interface with rope as one adapter. Rejected: rope is the reason this project exists, not a volatile dependency; there is no credible second engine; the port would be shaped by rope's capabilities anyway (a leaky abstraction) and would push tests towards mock engines, which the Testing Decisions explicitly reject.
- **Direct use with boundary translation (chosen)** — rope types flow freely *inside* the server but are confined by the four translation seams (Location Translator, Scope Resolver, Blast Radius Reporter, Uncertainty & Failure Mapper) and by boundary-level tests against real rope. Isolation is achieved at the tool boundary, not by indirection inside.

## Consequences

- rope types (`Project`, `ChangeSet`, refactoring classes, exceptions) may appear anywhere below the tool layer, but **never** in the tool layer's inputs or outputs — the published vocabulary (Location, Blast Radius, Uncertain Occurrence, Structured Failure) is the only thing that crosses.
- Tests assert behaviour at the tool boundary against real rope; no mock engine, no assertions on rope-internal types.
- If rope were ever replaced (no plan to), the rewrite cost is the server's internals — accepted, because the alternative is paying a permanent abstraction tax against a hypothetical.
