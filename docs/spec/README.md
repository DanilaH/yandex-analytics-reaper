# Living Specifications

`docs/spec/` contains the current analytical/domain source of truth. These files evolve with the system and should not be treated as dated research snapshots.

Recommended read order:

```text
system-principles.md
sources-and-capabilities.md
evidence-model.md
taxonomy.md
taxonomy-sampling.md
taxonomy-gold-set.md
taxonomy-primary-validation.md
taxonomy-agreement-analysis.md
taxonomy-controlled-agreement.md
production-assessment.md
market-observation.md
feed-depth-experiment.md
session-profile-stability-experiment.md
collection-cadence-experiment.md
search-query-family.md
comparable-set.md
analyst-experiment-runner.md
analyst-snapshot.md
listing-state-observations.md
analyst-market-export.md
analyst-market-features.md
analyst-semantic-enrichment.md
thesis-intelligence.md
thesis-intelligence-contracts-v1.md
thesis-intelligence-build-identity-v1.md
analyst-pilot-verification.md
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

`thesis-intelligence.md` owns the 0.3 product/analytical semantics. `thesis-intelligence-contracts-v1.md` freezes the exact v1 schemas and method boundaries. `thesis-intelligence-build-identity-v1.md` is the normative companion that freezes collision-safe rebuild identity/publication for multiple review states over one experiment artifact.

Do not duplicate roadmap phases in these specs. When a spec changes semantics that code already implements, update the implementation/tests in the same PR or explicitly record the implementation gap in `ROADMAP.md`.
