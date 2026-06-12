# Report uncertain occurrences rather than silently include or drop them

Because Python is dynamically typed, rope cannot always prove an occurrence refers to the Target (e.g. `obj.save()` where `obj`'s type is unknown). When a Refactoring runs, the server applies only the occurrences rope is certain about and enumerates every Uncertain Occurrence in the result as a flagged Location. The agent, which has ty and can read the code, adjudicates them, either re-running to include them or fixing by hand.

## Considered Options

- **Conservative (skip uncertain).** A skipped *real* occurrence silently leaves broken, half-renamed code.
- **Aggressive (apply all uncertain).** A false match silently makes a wrong edit elsewhere.
- **Report (chosen).** Apply certain matches, surface uncertain ones; every match is either applied openly or flagged, with nothing dropped or included in silence.

## Consequences

- The result schema must carry a list of Uncertain Occurrences (Locations) alongside the Blast Radius. The transparency principle is the same: the agent sees in full what was and wasn't touched.
- Whether a tool also offers an `include_uncertain` flag is an implementation shape choice; the surfacing requirement is not optional.
- Hard failures (rope raising `RefactoringError`) are returned as a Structured Failure stating the failed precondition, never a crash or stack trace. The failure's machine-readable reason uses the glossary vocabulary (Target, Location, Search Scope, …); rope's exception text may be carried as a supplementary detail field but is never the primary reason, so the Anti-Corruption Layer holds on the failure path too.
- An unparsable file in scope fails the Refactoring (Structured Failure naming the file) rather than being skipped: rope's `ignore_syntax_errors=True` would silently miss occurrences in the broken file, the same silent drop this ADR forbids. The agent fixes or reverts the named file and retries.
