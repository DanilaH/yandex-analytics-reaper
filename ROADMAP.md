# Roadmap

The roadmap is intentionally sequential. Finish and review each phase before expanding scope.

## Phase 1 — Foundation (current)

- [x] repository bootstrap
- [x] strict Python project configuration
- [x] capability interfaces
- [x] immutable raw snapshot store
- [x] evidence model
- [x] platform-neutral domain primitives
- [x] Yandex HTTP client
- [x] initial Yandex parsers
- [x] explicit probe CLI
- [x] fixture/unit tests
- [ ] independent review of bootstrap PR
- [ ] merge foundation

## Phase 2 — Yandex market state

- [ ] normalized listing persistence
- [ ] normalized metric persistence
- [ ] observation lineage persistence
- [ ] schema-drift registry
- [ ] feed-depth stability experiment (1/3/5/10 pages)
- [ ] session-profile stability experiment
- [ ] search query-family model
- [ ] comparable-set construction
- [ ] update/status/media histories
- [ ] decide actual collection cadence from observed volatility

Definition of done: given a timestamp, reconstruct the observed Yandex market state with provenance.

## Phase 3 — Taxonomy validation

- [ ] sample 100–200 diverse games
- [ ] create manual gold set
- [ ] validate primary core-loop labels
- [ ] confusion analysis
- [ ] revise taxonomy
- [ ] freeze first validated taxonomy version
- [ ] implement classifier only after schema stabilizes

Definition of done: comparable sets are consistent enough for market aggregation.

## Phase 4 — Opportunity discovery + candidate dossier

- [ ] aggregate supply/quality/traction features
- [ ] add transparent discovery heuristics
- [ ] candidate concept versioning
- [ ] production-assessment workflow
- [ ] evidence-coverage calculation
- [ ] BUILD/WATCH/SKIP policy implementation
- [ ] generate first end-to-end dossier

## Phase 5 — Historical backfill

- [ ] import available historical sources
- [ ] record timezone/data-lag/revision policy
- [ ] validate point-in-time integrity
- [ ] platform-policy regimes
- [ ] failure reason/censoring support

## Phase 6 — Backtesting

- [ ] strict point-in-time feature builder
- [ ] retrospective reconstruction kept separate
- [ ] simple baselines
- [ ] negative-filter validation
- [ ] interpretable market-prior model/ranker
- [ ] holdout evaluation

## Phase 7 — External trend enrichment

- [ ] Wordstat
- [ ] YouTube
- [ ] TGStat
- [ ] Google Trends if available
- [ ] optional cross-market sources

Add only signals that improve candidate decisions.

## Phase 8 — Own-game calibration

- [ ] freeze pre-build prediction snapshot
- [ ] actual development cost capture
- [ ] actual Yandex analytics/revenue import
- [ ] prediction/calibration error
- [ ] personalize production estimates and decision thresholds
