# Reaper 0.2.0 release acceptance — 2026-09-01

## Result

Reaper `0.2.0` / Analyst Experiment Runner v1.2 passed its real release acceptance. M1.5 is complete.

- merged release implementation: `ce2173bacaf63a34ba599a15d820e6f0a1ccbe72`
- final pre-merge quality gate: 356 tests passed, 84.28% total coverage, `ruff` PASS, strict `mypy` PASS
- real sweep: 15 families, 36 exact queries, 3 pages, 4 workers
- deliberate `SIGKILL` after completed query evidence existed
- same-workdir deterministic resume: PASS
- valid COMPLETED-query reuse: PASS
- stale interrupted RUNNING probe rejection: PASS
- final query total: 36 / 36
- unique comparable listings: 665
- rich metadata: 665 / 665
- final packaged verifier: PASS
- final resume invocation elapsed: ~35.33 s
- final immutable artifact SHA-256: `ea82be46229b63ac7a4966692c4d01ad6e24e1e58e7c13a9b5176f2a80d9342b`

The acceptance also served as the required M1.6 Mystery / Unboxing / Collection collection run. Compact permanent research inputs are stored under [`research/mystery-unboxing-collection-sweep-v1/`](../../research/mystery-unboxing-collection-sweep-v1/).

## Interpretation

This closes the runner engineering milestone. The same-day M1.6 decomposition of the 665-listing sweep selected `tactile-mystery-collectibles-v1` as a deliberately small heuristic BUILD probe, retained a stripped lucky-object reveal loop as WATCH, and rejected generic case/reskin strategies. M2 should start from that real candidate rather than from new runner/platform infrastructure.
