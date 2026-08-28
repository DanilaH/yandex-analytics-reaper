# Pre-development v2 Review Changelog

Historical record of the major changes made while hardening the pre-development specification into the current living specs.

## First adversarial review changes

1. Permission/privacy removed as development blockers for this private project.
2. Mixed taxonomy pseudo-archetypes separated into gameplay/theme/meta/social dimensions.
3. Taxonomy validation/gold set required before freeze.
4. Backtest leakage addressed with strict point-in-time vs retrospective reconstruction.
5. Selection bias made explicit: historical data validates a market prior, not a causal success probability.
6. Execution outcome separated from pre-build opportunity.
7. Historical platform-policy drift added.
8. Failure reasons/censoring added.
9. Single confidence grade replaced by independent evidence dimensions.
10. Source abstraction redesigned around capabilities.
11. Many-to-many raw→normalized lineage added.
12. Parser version removed from raw metadata.
13. Platform-neutral identity introduced.
14. Popular/editorial/sponsored/organic semantics separated.
15. Probe depth/frequency changed from constants to calibration experiments.
16. Session-profile bias added.
17. Search-result counts separated from comparable-game construction.
18. Historical estimate revision/point-in-time integrity added.
19. Explicit unknown-state semantics added.
20. BUILD/WATCH/SKIP decision policy added.
21. Opportunity Discovery added.
22. Production Assessment separated from market taxonomy.
23. Own-game calibration promoted to a core learning loop.

## Documentation-hardening review changes

1. Living specs moved from `docs/predev/` to `docs/spec/`; dated review history moved here.
2. Document ownership split across README / AGENTS / ARCHITECTURE / ROADMAP / spec / research / history.
3. Ingestion boundary corrected to `raw → parser → source DTO → normalizer → domain observation`.
4. Agent workflow hardened to repeated review/fix cycles, green CI, and final GitHub diff review.
5. Evidence time model split into `observed_at`, `available_at`, and `retrieved_at`.
6. Mutable freshness label removed from the stored evidence contract.
7. Historical availability separated from revision/recalculation status.
8. `editorial` removed conceptually from measurement kind and kept as exposure-selection semantics.
9. Taxonomy reframed as pragmatic primary gameplay archetype + controlled dimensions; `unknown` separated from `other`.
10. Probe runs/pages made explicit and stability experiments require a predeclared decision rule.
11. Backtests require a frozen BacktestSpec and untouched temporal holdout.
12. Generic normalized observation clarified as envelope/lineage anchor rather than a duplicate payload store.
13. Field-level lineage clarified as source field → target field + transformation version.
14. Cross-platform canonical game resolution explicitly deferred until needed.
15. Developer identity/history promoted to first-class analytical data.
16. Decision dimensions split into separate market-prior / production-fit / evidence-coverage scales.
17. Early decisions explicitly labeled `heuristic` until validation/calibration.
18. Opportunity Discovery split into Yandex-native Phase 4 and external-trend enrichment later.
19. Production-assessment labels require rubrics and the <=7-day constraint includes all production work.
20. Own-game calibration now appends evidence and changes policy only through explicit versioned reviews.
