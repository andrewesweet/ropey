# Operability

Every tool call emits one structured JSON record to **stderr** (stdout
belongs to the MCP stdio protocol):

```json
{"event": "refactoring-call", "tool": "rename", "root": "/path/to/repo",
 "scope_file_count": 2002, "lock_wait_ms": 0.0, "validate_ms": 20.8,
 "refactoring_ms": 216.3, "total_ms": 254.5, "outcome": "dry"}
```

Fields: resolved root, Search Scope file count, `validate()` ms (the
Freshness pass), refactoring ms, lock-wait ms, total ms, and the outcome
(`applied` / `dry` / `failure` with `failure_kind`). No metrics stack —
logs only (PRD Operability).

## Measured capacity envelope

Measured 2026-06-12 via `scripts/calibrate_envelope.py` (WSL2, Python
3.12, rope 1.14):

| Fixture | Files | Cold first call | Warm `validate()` | Warm call total | Peak RSS |
| ------- | ----- | --------------- | ----------------- | --------------- | -------- |
| small   | 52    | 19 ms           | 0.6 ms            | 8 ms            | 35 MB    |
| large   | 2 002 | 616 ms          | 21 ms             | 254 ms          | 49 MB    |

Against the PRD envelope: reality is comfortably **better** than the
order-of-magnitude expectations (cold ≈ hundreds of files/second parsed —
observed ~3 300 files/s; warm validate ≈ 10⁴–10⁵ stats/s — observed
~10⁵/s; memory tens of MB). No revision to the PRD envelope is needed.

### Rewrite match scan (PRD 0002)

The `rewrite` tool's record carries `match_scan_ms` (event
`rewrite-call`). The scan cost scales with Search Scope size, not match
count; a Match Constraint adds the extra certainty passes. Measured
2026-06-12, same rig, warm Project, every module matching:

| Scope files | Unconstrained | Name-constrained |
| ----------- | ------------- | ---------------- |
| 52          | 11 ms         | 25 ms            |
| 2 002       | 496 ms        | 947 ms           |

Against PRD 0002's envelope ("roughly seconds on a 1k-file project"):
observed under a second per 1 000 files even with constraints. No
revision needed.

## Phase 4 hook trigger

The hook accelerator triggers only if p50 `validate()` exceeds ~250 ms on
real repos. Observed: 21 ms at 2 000 files, extrapolating to ~1 s only at
100 k-file monorepo scale. On repos of the size ropey currently serves,
the trigger is **not** crossed. The go/no-go remains a human decision on
issue #20, using these logged timings.
