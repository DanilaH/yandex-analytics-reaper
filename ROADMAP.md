# Roadmap

`ROADMAP.md` is the single source of truth for implementation sequencing, current delivery milestones, and Definition of Done. Specifications describe semantics, not delivery order.

The roadmap is optimized for **time to useful analytical work**, not for completing every validation/research layer before the system can be used.

The project keeps the same evidence-honesty rules:

- synthetic fixtures prove tooling mechanics only;
- an unfinished empirical task cannot be consumed as if its conclusion were known;
- provisional/manual/heuristic outputs must be labeled as such;
- calibration, taxonomy validation, historical backtesting, and portfolio calibration increase confidence but do not automatically block earlier human-in-the-loop analysis;
- no downstream threshold, policy, validation result, or analytical claim may pretend to use evidence that has not actually been collected.

## Delivery strategy

The useful product loop is:

```text
real Yandex evidence
→ reproducible current-market snapshot
→ explicit comparable set
→ analyst-readable market features
→ candidate hypothesis
→ traceable dossier
→ heuristic BUILD / WATCH / SKIP
```

There are two near-term product gates:

```text
START ANALYSIS
human analyst can reproducibly inspect current niches/comparables and their evidence

FIRST DECISION LOOP
candidate can be evaluated end to end into a traceable heuristic portfolio decision
```

Long-running calibration and validation work proceeds in parallel when possible. It becomes a hard dependency only when a later feature would otherwise falsely present an unvalidated result as validated.

A dashboard, ML model, scheduler, external trend source, historical backtest, validated taxonomy, or automatic classifier is **not** required to reach `START ANALYSIS`.

---

## M0 — Trustworthy evidence foundation — COMPLETE

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
- [x] source DTO → normalizer boundary
- [x] normalized listing/developer persistence
- [x] normalized metric persistence
- [x] observation + field-level lineage persistence
- [x] schema-drift registry with field/type/missingness checks
- [x] probe-run/page grouping
- [x] explicit `clean_anonymous` / persistent-session semantics
- [x] search query-family model
- [x] provisional `yandex_search_union_v1` comparable-set construction
- [x] update/status/media histories
- [x] shared versioned SQLite migrations
- [x] reviewed living analytical specifications

**Definition of Done:** raw Yandex evidence can be collected, replayed, normalized, stored with lineage, and reconstructed without silently collapsing source uncertainty.

---

# PRIMARY PATH — GET TO USEFUL ANALYTICS

## M1 — Analyst Workbench v0 — `START ANALYSIS`

Goal: make the existing evidence/market-state foundation operable as one reproducible analyst workflow. This milestone does **not** require automated discovery, a validated taxonomy/classifier, historical backtesting, or empirically optimal collection parameters.

Early analysis is intentionally based on **explicit query families + reproducible search-derived comparable sets**. Taxonomy becomes important when the system needs to aggregate or discover opportunities automatically across the broader market; it is not a prerequisite for a human analyst to compare concrete niches.

### M1.1 — Reproducible analyst collection

Already available:

- [x] manual raw-first feed collection
- [x] manual raw-first search collection with exact query text and `totalGamesCount`
- [x] rich `get_games` metadata collection + normalization
- [x] game-page metadata collection + normalization
- [x] explicit probe context/session/run provenance
- [x] immutable query-family declaration/storage model
- [x] reproducible search-derived comparable-set builder/storage model

Still required for analyst use:

- [x] expose query-family declaration/persistence through a supported operator-facing CLI/file workflow
- [x] expose `yandex_search_union_v1` comparable-set construction through a supported operator-facing CLI/file workflow
- [x] add a small reproducible **analyst snapshot manifest/workflow** that binds the exact feed/search/query-family/rich-metadata evidence used for one analysis session
- [x] require the snapshot to record explicit collection context/depth/session choices and label still-uncalibrated choices as provisional rather than hiding them behind an “optimal” default
- [x] fail closed when an analyst snapshot mixes incompatible contexts or incomplete/failed evidence

Pending feed-depth/session/cadence experiments remain pending and must not be reverse-engineered from whatever explicit parameters were used in an early analyst snapshot.

### M1.2 — Analyst-readable market snapshot

- [x] add a read/export boundary over persisted observations instead of requiring direct SQLite inspection
- [x] export current listing identity/title/developer/basic metadata with evidence references
- [x] export available `gqRating`, player rating, `ratingCount`, publication/update metadata, and known missingness
- [x] export feed/search exposure observations separately from game metrics
- [x] export search `totalGamesCount` as a query-supply signal, never a canonical competitor count
- [x] export comparable-set membership with exact source query/run/raw provenance
- [x] provide JSON and/or CSV artifacts suitable for manual analysis; no dashboard is required

### M1.3 — Minimal comparable-market features

Compute only transparent current-state features that are supported by already proven public Yandex data:

- [x] comparable-set size / observed supply
- [x] query-level search-supply observations
- [x] `gqRating` distribution and coverage
- [x] player-rating / `ratingCount` distribution and coverage
- [x] first-published / recent-release distribution where source data is present
- [x] organic feed/search exposure summaries from the explicit analyst snapshot
- [x] developer concentration/basic supply composition where evidence permits
- [x] missing/unknown/evidence-coverage diagnostics alongside every aggregate

Do **not** fabricate unavailable competitor DAU, retention, playtime, CTR, revenue, or ARPDAU.

Taxonomy is optional at this milestone. If an analyst manually attaches draft taxonomy labels during exploratory work, those labels must remain explicitly provisional and must not be presented as validated classifier output.

### M1.4 — Real analyst pilot

- [ ] collect one real analyst snapshot from current Yandex evidence
- [ ] build at least two explicit comparable sets for real game hypotheses/niches
- [ ] produce the analyst-readable exports/features for those sets
- [ ] independently trace representative aggregates back to normalized observations and raw snapshots
- [ ] record limitations/unknowns exposed by the pilot and fix only blockers to practical analysis

### `START ANALYSIS` gate

`START ANALYSIS` is reached when a human analyst can, from supported commands/files:

```text
collect real Yandex evidence
→ declare an explicit query family / market question
→ construct a reproducible comparable set
→ inspect current supply/quality/traction-proxy evidence
→ compare multiple niches/hypotheses
→ see missingness + provenance for the result
```

At this point **analytical activity should begin**. Do not postpone real use merely because calibration, taxonomy validation, historical backtesting, external trends, or automation are unfinished.

**Release notification requirement:** do not silently cross this gate. Only after every `START ANALYSIS` condition has been verified against the real analyst workflow/pilot, explicitly tell the project owner/user that **Analyst Workbench v0 is ready for analytical use and analytical activity can begin**. Do not make that readiness claim early, and do not move on to M2 without giving the explicit notification once the gate is genuinely satisfied.

---

## M2 — Candidate Dossier v0 — `FIRST DECISION LOOP`

Goal: turn human-selected market hypotheses into explicit, inspectable decisions without pretending the policy has been historically validated.

### M2.1 — Candidate identity and evidence package

- [ ] candidate concept versioning
- [ ] bind each candidate to its exact analyst snapshot/comparable-set versions
- [ ] preserve supporting evidence, counter-evidence, unknowns, and evidence coverage
- [ ] make every derived market feature traceable to its source observations/raw evidence

### M2.2 — Production assessment

- [ ] freeze v1 rubrics for dev complexity, assets, content, backend, balancing, liveops, QA, mobile adaptation, and AI-assisted fit
- [ ] implement the candidate-specific production-assessment workflow
- [ ] store estimated MVP day range, major risks, reusable systems, tooling profile, and assessment version
- [ ] keep production feasibility separate from market taxonomy

### M2.3 — Heuristic market prior + decision policy

- [ ] implement decomposable current-market prior inputs from M1 features
- [ ] implement evidence-coverage calculation
- [ ] implement provisional BUILD / WATCH / SKIP policy
- [ ] label every pre-backtest decision `heuristic`
- [ ] require rationale, counter-evidence, unknowns, and appropriate WATCH/SKIP follow-up conditions
- [ ] do not introduce an opaque opportunity score

### M2.4 — Dossier artifact

- [ ] generate one stable human-readable candidate dossier artifact
- [ ] include candidate thesis, comparable set, market evidence, production assessment, evidence coverage, decision, and raw/normalized evidence references
- [ ] support freezing a pre-build dossier/decision snapshot so later outcomes cannot rewrite the original thesis

### M2.5 — First real decision loop

- [ ] run at least one real candidate from current Yandex evidence through the complete dossier flow
- [ ] independently review whether another analyst can reconstruct why the decision was made
- [ ] fix usability/evidence gaps found by the real dossier

### `FIRST DECISION LOOP` gate

```text
real current-market evidence
→ candidate
→ comparable analysis
→ production assessment
→ evidence coverage
→ dossier
→ heuristic BUILD / WATCH / SKIP
```

This is the first complete useful product loop. Backtesting later determines whether the heuristic policy deserves stronger validation status.

---

## M3 — Yandex-native opportunity discovery v0

Goal: reduce the amount of manual idea generation once M1/M2 have proved that the underlying evidence and dossiers are useful.

- [ ] aggregate Yandex-native supply/quality/traction-proxy features across eligible market seeds
- [ ] add transparent/versioned discovery heuristics
- [ ] surface candidate seeds with an explicit `why surfaced` explanation
- [ ] dedupe candidate concepts / avoid obvious repeated hypotheses
- [ ] apply production feasibility after market-seed generation, not inside taxonomy
- [ ] preserve source feature snapshot/version for every surfaced candidate
- [ ] feed surfaced candidates into the M2 dossier workflow
- [ ] keep discovery results labeled heuristic until historical evaluation exists

A validated taxonomy/classifier improves scale and consistency. Until it lands, any taxonomy-driven automatic discovery must remain explicitly provisional or be restricted to analyst-reviewed labels. Query-family-driven exploration can continue independently.

**Definition of Done:** the system can surface plausible current Yandex-native candidate hypotheses and route them into the already-proven dossier loop.

---

# PARALLEL EVIDENCE / VALIDATION TRACKS

These tracks increase confidence and eventually replace provisional collection/taxonomy assumptions. They do **not** block `START ANALYSIS` unless a specific analytical feature would otherwise consume their unfinished conclusion.

## V1 — Market-collection calibration

### Feed depth

- [x] freeze `feed-depth-v1` protocol and merge replay/analyzer tooling
- [ ] execute the empirical calibration with the frozen minimum sample/time-span guards
- [ ] record the resulting depth decision
- [ ] replace early analyst collection parameters only through an explicit versioned operating-profile change

### Session profile

- [x] freeze `session-profile-stability-v1` protocol and merge matched-block replay/analyzer tooling
- [ ] execute the empirical matched-block calibration with the frozen sample/time/order guards
- [ ] record per-depth classifications
- [ ] change analyst/production session policy only if the real evidence supports it

### Collection cadence

- [x] freeze `collection-cadence-v1` protocol
- [x] merge immutable pre-collection plan + raw-first reference/downsampling replay tooling
- [ ] execute at least 28 consecutive daily reference checkpoints
- [ ] record capability/depth cadence decisions
- [ ] introduce scheduled production collection only after the cadence policy is explicit

**Important:** the 28-day cadence experiment is a calendar-bound calibration task, not a reason to delay current on-demand analysis.

## V2 — Taxonomy validation and classifier

### Existing tooling

- [x] revise the original draft into a pragmatic primary archetype + controlled-dimensions model
- [x] add `unknown` distinct from `other`
- [x] define/version controlled registries for mechanics/objectives/meta/tone
- [x] freeze `taxonomy-diversity-sample-v1` deterministic sampler tooling
- [x] freeze manual annotation/adjudication contracts and gold-set tooling
- [x] freeze primary-archetype validation/review protocol and tooling
- [x] freeze primary independent-annotation agreement/confusion tooling
- [x] freeze controlled-dimension exact-set agreement + per-label gold-alignment tooling

### Still required

- [ ] freeze the theme-canonicalization validation protocol/tooling required by the taxonomy specification
- [ ] execute the sampler against real persisted Yandex evidence and record the 100–200-listing sample identity/hash
- [ ] execute genuine independent manual annotation/adjudication and record the gold-set identity/hash
- [ ] execute primary-archetype review against the real gold set
- [ ] execute real primary agreement/confusion analysis
- [ ] execute real controlled-dimension agreement analysis
- [ ] execute real theme-canonicalization analysis
- [ ] revise taxonomy from the completed empirical evidence
- [ ] freeze the first validated taxonomy version
- [ ] implement classifier only after schema stabilizes
- [ ] build taxonomy-refined comparable-set construction as a new explicit construction version

**Definition of Done:** automated taxonomy use is consistent enough for scalable market aggregation; low-confidence cases remain explicitly unknown.

---

# POST-USEFUL-LOOP VALIDATION AND SCALE

## M4 — Operational collection automation

Do this after the manual analyst workflow has proved what actually needs automation.

- [ ] automate query-family execution/batch collection
- [ ] add scheduled collection using the empirically selected cadence
- [ ] add authenticated-test credential/profile provider only if a concrete analysis needs that context
- [ ] define retry/recovery/operational reporting for scheduled runs
- [ ] preserve the same raw-first, context, lineage, and schema-drift guarantees as manual probes

A dashboard remains optional. Build one only if repeated analyst use shows that CLI/JSON/CSV artifacts materially slow the workflow.

---

## M5 — Historical backfill

- [ ] import available historical sources
- [ ] record source timezone, data lag, revision policy, and `available_at` semantics
- [ ] distinguish historical availability from revision/recalculation status
- [ ] validate strict point-in-time eligibility
- [ ] model platform-policy regimes
- [ ] add failure reason/censoring support
- [ ] add near-duplicate/template-family metadata where feasible

**Definition of Done:** historical observations clearly declare whether they can be used in strict point-in-time analysis.

---

## M6 — Backtesting and policy validation

- [ ] freeze versioned `BacktestSpec` before final holdout evaluation
- [ ] build strict point-in-time features using `available_at`
- [ ] keep retrospective reconstruction separate
- [ ] evaluate decision horizons (at least 7d/14d/30d where data permits)
- [ ] implement simple baselines
- [ ] validate negative filters
- [ ] evaluate discovery heuristics against baselines
- [ ] build an interpretable market-prior model/ranker only if it adds measurable value
- [ ] add group-aware leakage controls for obvious template/reskin families where feasible
- [ ] perform untouched temporal holdout evaluation
- [ ] promote decision policy status from `heuristic` only if the evidence supports it

**Definition of Done:** recommended candidates beat simple baselines on an untouched temporal holdout without known time/data leakage.

---

## M7 — External trend enrichment

- [ ] Wordstat
- [ ] YouTube
- [ ] TGStat
- [ ] Google Trends if available
- [ ] optional cross-market sources
- [ ] measure whether each external signal improves candidate discovery/decisions

External trends enrich the proven Yandex-native loop; they are not prerequisites for `START ANALYSIS` or the first dossier.

---

## M8 — Own-game calibration

- [ ] freeze immutable pre-build prediction/dossier snapshot for each actual release
- [ ] capture actual development cost
- [ ] import actual Yandex analytics/revenue
- [ ] append realized outcome cohorts after every release
- [ ] run periodic, versioned production/decision calibration reviews
- [ ] personalize production estimates and decision thresholds

Do not silently update thresholds after every release. Each calibration change creates a new explicit assessment/policy version.

---

# Scope guard

Before `START ANALYSIS`, reject work that does not materially improve at least one of:

```text
reproducible real-data collection
comparable-set construction
analyst-readable market evidence
transparent current-market aggregation
provenance / missingness visibility
```

Before `FIRST DECISION LOOP`, reject work that does not materially improve:

```text
candidate evidence package
production assessment
evidence coverage
dossier usability
explicit heuristic decision-making
```

In particular, do not let dashboard work, ML/ranking, orchestration frameworks, broad external-source integrations, extra taxonomy machinery, or additional statistical protocols displace the shortest path to actual analyst use.
