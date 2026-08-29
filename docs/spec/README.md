# Living Specifications

`docs/spec/` contains the current analytical/domain source of truth. These files evolve with the system and should not be treated as dated research snapshots.

Recommended read order:

```text
system-principles.md
sources-and-capabilities.md
evidence-model.md
taxonomy.md
production-assessment.md
market-observation.md
feed-depth-experiment.md
session-profile-stability-experiment.md
search-query-family.md
comparable-set.md
listing-histories.md
historical-backtesting.md
data-model.md
decision-policy.md
opportunity-discovery.md
own-game-calibration.md
```

Ownership reminder:

```text
/ARCHITECTURE.md  code/runtime boundaries
/ROADMAP.md       implementation sequencing and Definition of Done
/docs/spec/*      analytical/domain semantics
/docs/research/*  dated factual observations/probes
/docs/history/*   historical review/decision records
```

Do not duplicate roadmap phases in these specs. When a spec changes semantics that code already implements, update the implementation/tests in the same PR or explicitly record the implementation gap in `ROADMAP.md`.
