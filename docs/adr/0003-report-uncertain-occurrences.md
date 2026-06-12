# Report uncertain occurrences rather than silently include or drop them

Because Python is dynamically typed, rope cannot always prove an occurrence refers to the Target (e.g. `obj.save()` where `obj`'s type is unknown). When a Refactoring runs, the server applies only the occurrences rope is certain about and enumerates every Uncertain Occurrence in the result as a flagged Location. The agent — which has ty and can read the code — adjudicates them, either re-running to include them or fixing by hand.

## Considered Options

- **Conservative (skip uncertain)** — a skipped *real* occurrence silently leaves broken, half-renamed code.
- **Aggressive (apply all uncertain)** — a false match silently makes a wrong edit elsewhere.
- **Report (chosen)** — apply certain matches, surface uncertain ones; no silent inclusion, no silent drop.

## Consequences

- The result schema must carry a list of Uncertain Occurrences (Locations) alongside the Blast Radius. Same transparency principle: the agent always sees the full truth of what was and wasn't touched.
- Whether a tool also offers an `include_uncertain` flag is an implementation shape choice; the surfacing requirement is not optional.
- Hard failures (rope raising `RefactoringError`) are returned as a Structured Failure stating the failed precondition, never a crash or stack trace.
