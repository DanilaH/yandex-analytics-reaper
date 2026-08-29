# AGENTS.md

This repository is intended to be worked on by human developers and coding agents.

## Read-first order

Before implementing a task, read:

1. `ARCHITECTURE.md` — code/runtime boundaries;
2. `ROADMAP.md` — current phase, sequencing, entry/exit criteria;
3. the relevant living specification under `docs/spec/`;
4. relevant factual evidence under `docs/research/` when the task depends on a proven source behavior;
5. existing tests around the touched boundary.

## Documentation ownership

Each question has one authoritative owner:

```text
README.md       onboarding, current repository status, local commands
AGENTS.md       agent workflow and engineering discipline
ARCHITECTURE.md package/runtime boundaries and dependency direction
ROADMAP.md      sequencing, current phase, Definition of Done

docs/spec/*     living analytical/domain specifications
docs/research/* dated factual observations and experiments
docs/history/*  historical decision/review records
```

Do not duplicate roadmap sequencing inside specifications. If an architectural decision changes, update the owning document in the same PR.

## Non-negotiable architecture rules

- Preserve raw source responses before parsing/normalization.
- Raw snapshots are immutable and parser-independent.
- Keep the ingestion boundary explicit:

```text
CollectedResponse
→ RawSnapshot
→ source parser(version)
→ source DTO
→ normalizer(version)
→ domain observation
```

- Source DTOs must not leak into analytics/domain layers.
- Do not let domain code depend directly on Yandex JSON shapes.
- Source integrations implement capabilities; do not create a god `YandexSource` interface.
- Every derived decision-relevant value must be traceable through normalized observations to raw snapshots.
- Keep observed, estimated, derived, and inferred evidence distinct. Editorial/sponsored/organic are exposure-selection semantics, not measurement kinds.
- Never silently reinterpret missing values; use explicit unknown/missing reasons.
- Do not treat `totalGamesCount` as canonical competitor count.
- Keep sponsored/editorial exposure separate from organic recommendation exposure.
- Do not introduce an opaque Opportunity Score before backtesting validates its components.
- Backtests must declare strict point-in-time vs retrospective reconstruction and enforce `available_at` semantics.
- Production assessment is separate from market taxonomy.
- Avoid architectural scope creep: no dashboard, streaming stack, ClickHouse, ML platform, or orchestration framework until the roadmap reaches them.
- Network calls are forbidden in unit tests.
- Keep typing strict and changes small enough to review.

## Change discipline

For every roadmap task:

```text
task
→ implementation
→ focused tests
→ independent review against code + owning docs
→ fix
→ re-review
→ repeat until no blocking findings
→ full quality checks / CI when runnable
→ final GitHub diff review
→ merge
→ update roadmap/current status
→ next task
```

Rules:

- A real Ruff, mypy, pytest, build, or application test failure is a merge blocker.
- A CI infrastructure failure that occurs before quality steps execute (for example no runner allocation / zero executed steps) is **not** itself a merge blocker. Confirm that the workflow/config was not changed into a broken state, record the infrastructure limitation, run the strongest available local/focused substitutes, perform the final GitHub diff review, and continue.
- Never classify an unknown CI failure as infrastructure-only merely to merge. The evidence must show that quality steps did not execute or that the failure is external to the code under review.
- Never make CI green by weakening Ruff, mypy, tests, or other quality gates unless the rule itself is independently shown to be wrong and the rationale is documented.
- Passing tests do not replace independent review.
- Review the actual GitHub diff before merge, not only a local working copy.
- Do not ask the user to perform routine implementation review; escalate only genuinely external/product decisions or unavailable access.
- Do not incidentally reorder the roadmap inside an implementation task. Change sequencing explicitly in `ROADMAP.md` with rationale.
- If parser behavior or interpretation changes, bump the parser version and add fixture-driven regression tests. A source adding an irrelevant field does not by itself require a parser-version bump.
- If schema profiling or drift-evaluation semantics change, bump the schema analyzer version so immutable raw snapshots can be re-analyzed without reusing stale cached analyses.
- If an explicit source schema contract changes semantically, create a new versioned `contract_id`; never mutate the meaning of an existing contract ID in place.
- Never silently make parsers accept arbitrary schema drift.
