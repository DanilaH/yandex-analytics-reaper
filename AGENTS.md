# AGENTS.md

This repository is intended to be worked on by human developers and coding agents.

## Read-first order

Before implementing a task, read:

1. `ARCHITECTURE.md`
2. `ROADMAP.md`
3. the relevant document under `docs/predev/`
4. existing tests around the touched boundary

## Non-negotiable rules

- Preserve raw source responses before normalization.
- Raw snapshots are immutable and parser-independent.
- Do not let domain code depend directly on Yandex JSON shapes.
- Source integrations implement capabilities; do not create a god `YandexSource` interface.
- Every derived decision-relevant value must be traceable to normalized observations/raw snapshots.
- Keep observed, estimated, derived, inferred, and editorial evidence distinct.
- Never silently reinterpret missing values; use explicit unknown/missing reasons.
- Do not treat `totalGamesCount` as canonical competitor count.
- Keep sponsored/editorial exposure separate from organic recommendation exposure.
- Do not introduce an opaque Opportunity Score before a backtest validates its components.
- Backtests must declare `strict_point_in_time` vs `retrospective_reconstruction`.
- Production assessment is separate from market taxonomy.
- Avoid architectural scope creep: no dashboard, streaming stack, ClickHouse, ML platform, or orchestration framework until the roadmap reaches them.
- Network calls are forbidden in unit tests.
- Keep typing strict and code small enough to review.

## Change discipline

For each task:

```text
task
→ implementation
→ focused tests
→ independent review against docs
→ fixes
→ full quality checks
→ merge
```

If a source schema changes, update a parser version and add fixture-driven tests. Do not silently make parsers accept everything.
