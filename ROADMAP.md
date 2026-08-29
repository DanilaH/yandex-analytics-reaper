# Roadmap

`ROADMAP.md` is the single source of truth for implementation sequencing, current phase, and phase Definition of Done. Specifications describe semantics, not delivery order.

Finish, independently review, and merge each task/phase before expanding scope unless the roadmap is explicitly amended.

For a time-gated empirical task whose completion requires observations across a real time window, protocol/tooling and empirical execution may be tracked separately. Once the protocol/tooling is merged and frozen, preparation of the next isolated roadmap task may proceed while empirical collection is pending. This exception does **not** permit consuming an unfinished experiment as evidence: no downstream default, threshold, policy, or analytical conclusion may depend on that experiment until its empirical completion item is checked off.

## Phase 1 — Foundation

- [x] repository bootstrap
- [x] strict Python project configuration
- [x] capability interfaces
- [x] immutable raw snapshot store
- [x] evidence/domain/taxonomy/candidate primitives
- [x] Yandex HTTP client
- [x] source-specific parsers for current proven Yandex surfaces
- [x] explicit manual probe CLI
- [x] fixture/unit tests
- [x] living specification structure and agent workflow
- [x] independent final diff review
- [x] green `ruff check .`
- [x] green `mypy src`
- [x] green `pytest`

**Definition of Done:** the repository has strict quality gates, immutable raw capture, source/capability boundaries, source DTO parsing, reviewed living specs, and no known blocking review findings. Normalized market-state persistence is intentionally not part of Phase 1.

Phase 1 is complete when this foundation lands on `main`.

## Phase 2 — Yandex market state

- [x] introduce explicit source DTO → normalizer boundary
- [x] normalized listing/developer persistence
- [x] normalized metric persistence
- [x] observation + field-level lineage persistence
- [x] schema-drift registry with field/type/missingness checks
- [x] probe-run/page grouping
- [x] define `clean_anonymous` / persistent session semantics
- [ ] feed-depth stability experiment (1/3/5/10 pages) with predeclared decision rule
  - [x] freeze `feed-depth-v1` protocol and merge replay/analyzer tooling
  - [ ] execute the empirical calibration with the frozen minimum sample/time-span guards and record the resulting depth decision
- [ ] session-profile stability experiment
- [ ] search query-family model
- [ ] comparable-set construction
- [ ] update/status/media histories
- [ ] decide actual collection cadence from measured volatility

**Definition of Done:** given an `as_of` timestamp, reconstruct the observed Yandex market state with source lineage and known observation coverage.

## Phase 3 — Taxonomy validation

- [ ] revise draft taxonomy into a pragmatic primary gameplay-archetype + controlled dimensions model
- [ ] add `unknown` distinct from `other`
- [ ] define/version controlled label registries for mechanics/objectives/meta/tone
- [ ] sample 100–200 diverse Yandex games
- [ ] create manual gold set
- [ ] validate primary gameplay-archetype labels
- [ ] confusion analysis / agreement analysis
- [ ] revise taxonomy
- [ ] freeze first validated taxonomy version
- [ ] implement classifier only after schema stabilizes

**Definition of Done:** comparable-game sets are consistent enough for market aggregation and low-confidence cases can remain explicitly unknown.

## Phase 4 — Yandex-native opportunity discovery + candidate dossier

- [ ] aggregate Yandex-native supply/quality/traction-proxy features
- [ ] add transparent/versioned discovery heuristics
- [ ] candidate concept versioning
- [ ] production-assessment workflow + rubrics
- [ ] evidence-coverage calculation
- [ ] implement provisional BUILD/WATCH/SKIP policy
- [ ] label decisions as `heuristic` until backtest validation exists
- [ ] generate first end-to-end dossier

**Definition of Done:** current Yandex-native data can surface candidate seeds and produce a traceable provisional dossier without external trend sources.

## Phase 5 — Historical backfill

- [ ] import available historical sources
- [ ] record source timezone, data lag, revision policy, and `available_at` semantics
- [ ] distinguish historical availability from revision/recalculation status
- [ ] validate strict point-in-time eligibility
- [ ] platform-policy regimes
- [ ] failure reason/censoring support
- [ ] near-duplicate/template-family metadata where feasible

**Definition of Done:** historical observations clearly declare whether they can be used in strict point-in-time analysis.

## Phase 6 — Backtesting

- [ ] freeze versioned BacktestSpec before final holdout evaluation
- [ ] strict point-in-time feature builder using `available_at`
- [ ] retrospective reconstruction kept separate
- [ ] evaluate decision horizons (at least 7d/14d/30d where data permits)
- [ ] simple baselines
- [ ] negative-filter validation
- [ ] interpretable market-prior model/ranker
- [ ] group-aware leakage controls for obvious template/reskin families where feasible
- [ ] untouched temporal holdout evaluation
- [ ] promote decision policy status from `heuristic` only if evidence supports it

**Definition of Done:** recommended candidates beat simple baselines on an untouched temporal holdout without known time/data leakage.

## Phase 7 — External trend enrichment

- [ ] Wordstat
- [ ] YouTube
- [ ] TGStat
- [ ] Google Trends if available
- [ ] optional cross-market sources
- [ ] measure whether each external signal improves candidate decisions

External trends enrich the Phase 4 discovery/dossier system; they are not prerequisites for its first Yandex-native version.

## Phase 8 — Own-game calibration

- [ ] freeze immutable pre-build prediction/dossier snapshot
- [ ] actual development cost capture
- [ ] actual Yandex analytics/revenue import
- [ ] append realized outcome cohorts after every release
- [ ] periodic, versioned production/decision calibration review
- [ ] personalize production estimates and decision thresholds

Do not silently update thresholds after every release. Each calibration change creates a new explicit assessment/policy version.
