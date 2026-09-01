# Roadmap

`ROADMAP.md` is the single source of truth for implementation sequencing, current delivery
milestones, and Definition of Done. Specifications describe semantics; this file decides what is
built next and what is deliberately deferred.

The roadmap is optimized for **time to useful analytical work**. The project does not complete
infrastructure, validation, or automation layers merely because they are conceptually desirable.

Evidence-honesty rules remain unchanged:

- synthetic fixtures prove tooling mechanics only;
- unfinished empirical work cannot be consumed as if its conclusion were known;
- provisional/manual/heuristic outputs must be labeled as such;
- calibration, taxonomy validation, historical backtesting, and portfolio calibration increase
  confidence but do not automatically block earlier human-in-the-loop analysis;
- no downstream threshold, policy, validation result, or analytical claim may pretend to use
  evidence that has not actually been collected.

---

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

Product gates:

```text
START ANALYSIS
human analyst can reproducibly inspect current niches/comparables and their evidence

FIRST DECISION LOOP
candidate can be evaluated end to end into a traceable heuristic portfolio decision
```

`START ANALYSIS` has already been reached. The current blocker is narrower: the analyst experiment
runner can execute real sweeps, but long sweeps are still operationally fragile because execution
is silent, foreground-shell interruption destroys useful progress, and exact queries are collected
sequentially.

Therefore the immediate delivery sequence is:

```text
M1 complete
→ Reaper 0.2.0 / Analyst Experiment Runner v1.2
→ real Mystery / Unboxing / Collection sweep
→ manual opportunity decomposition
→ 1–3 concrete ultra-low-production-burden candidate theses
→ M2 dossier / FIRST DECISION LOOP
```

Do **not** replace the real post-`0.2.0` sweep with another infrastructure milestone.

Long-running calibration and validation work continues in parallel when useful. It becomes a hard
dependency only when a later feature would otherwise falsely present an unvalidated result as
validated.

A dashboard, ML model, scheduler, external trend source, historical backtest, validated taxonomy,
or automatic classifier is not required for the current delivery path.

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

**Definition of Done:** raw Yandex evidence can be collected, replayed, normalized, stored with
lineage, and reconstructed without silently collapsing source uncertainty.

---

# PRIMARY PATH — GET TO USEFUL ANALYTICS

## M1 — Analyst Workbench v0 — `START ANALYSIS` — COMPLETE

Goal: make the evidence/market-state foundation operable as one reproducible analyst workflow.
This milestone does not require automated discovery, a validated taxonomy/classifier, historical
backtesting, or empirically optimal collection parameters.

Early analysis is intentionally based on **explicit query families + reproducible search-derived
comparable sets**. Taxonomy becomes important when the system must aggregate or discover
opportunities automatically across the broader market; it is not a prerequisite for a human
analyst comparing concrete niches.

### M1.1 — Reproducible analyst collection

Already available:

- [x] manual raw-first feed collection
- [x] manual raw-first search collection with exact query text and `totalGamesCount`
- [x] rich `get_games` metadata collection + normalization
- [x] game-page metadata collection + normalization
- [x] explicit probe context/session/run provenance
- [x] immutable query-family declaration/storage model
- [x] reproducible search-derived comparable-set builder/storage model
- [x] supported query-family declaration/persistence workflow
- [x] supported `yandex_search_union_v1` comparable-set workflow
- [x] reproducible analyst snapshot manifest/workflow
- [x] explicit provisional collection context/depth/session choices
- [x] fail-closed snapshot compatibility and evidence completeness

Pending feed-depth/session/cadence experiments remain pending and must not be reverse-engineered
from whatever explicit parameters were used in an early analyst snapshot.

### M1.2 — Analyst-readable market snapshot

- [x] persisted-observation read/export boundary
- [x] current listing identity/title/developer/basic metadata with evidence references
- [x] `gqRating`, player rating, `ratingCount`, publication/update metadata, and missingness
- [x] feed/search exposure observations separated from game metrics
- [x] search `totalGamesCount` exported only as a query-supply signal
- [x] comparable-set membership with exact source query/run/raw provenance
- [x] JSON/CSV artifacts suitable for manual analysis

### M1.3 — Minimal comparable-market features

- [x] comparable-set size / observed supply
- [x] query-level search-supply observations
- [x] `gqRating` distribution and coverage
- [x] player-rating / `ratingCount` distribution and coverage
- [x] first-published / recent-release distribution where present
- [x] organic feed/search exposure summaries
- [x] developer concentration/basic supply composition where evidence permits
- [x] missing/unknown/evidence-coverage diagnostics alongside aggregates

Do not fabricate unavailable competitor DAU, retention, playtime, CTR, revenue, or ARPDAU.

Taxonomy is optional here. Analyst-attached draft labels remain explicitly provisional.

### M1.4 — Real analyst pilot

- [x] collect one real analyst snapshot
- [x] build at least two explicit comparable sets for real hypotheses/niches
- [x] produce analyst-readable exports/features
- [x] trace representative aggregates to normalized observations and raw snapshots
- [x] record and fix blockers exposed by the pilot

Evidence record:
[`docs/history/analyst-pilot-2026-08-30.md`](docs/history/analyst-pilot-2026-08-30.md).

The pilot found no blocker to practical human-in-the-loop analysis. Collection parameters and
search-derived comparables remain provisional. Query-family coherence can vary materially and is
an analyst-visible judgment rather than a hidden assumption.

### `START ANALYSIS` gate — REACHED 2026-08-30

```text
collect real Yandex evidence
→ declare explicit query family / market question
→ construct reproducible comparable set
→ inspect current supply/quality/traction-proxy evidence
→ compare niches/hypotheses
→ inspect missingness + provenance
```

Analytical activity must not be postponed merely because calibration, taxonomy validation,
historical backtesting, external trends, or broad automation are unfinished.

---

## M1.5 — Reaper `0.2.0` / Analyst Experiment Runner v1.2 — IN PROGRESS

**Current highest-priority implementation milestone.**

Goal: make the already-useful analyst workflow safe and practical for larger real market sweeps.

Real usage exposed three concrete operational blockers:

```text
silent long-running execution
+ no recovery after foreground-process interruption
+ sequential exact-query collection
```

This milestone fixes those blockers without changing the analyst-owned manifest semantics or
building a generic orchestration platform.

Normative implementation contract:

```text
docs/spec/analyst-experiment-runner.md
workflow: analyst-experiment-v1.2
release: Reaper 0.2.0
manifest schema: remains v1
```

The specification file must be upgraded from v1.1 to the reviewed v1.2 contract as part of this
milestone.

### M1.5.1 — Run identity + observability

- [ ] bump workflow contract to `analyst-experiment-v1.2`
- [ ] persist immutable `run-state.json` before first network request
- [ ] preserve verbatim workdir-owned input manifest + SHA-256 identity
- [ ] add exclusive process-owned workdir locking
- [ ] add one structured runner-event boundary
- [ ] append human-readable `logs/run.log`
- [ ] append machine-readable `logs/events.jsonl`
- [ ] emit stage/query/page/retry progress in non-interactive shells
- [ ] add 15-second inactivity heartbeat
- [ ] add monotonic stage/query/page/rich-batch timings
- [ ] write packaged `reports/execution-timings.json`
- [ ] print explicit terminal failure context and concrete resume command
- [ ] keep logs/progress operational; never use them as evidence authority

### M1.5.2 — Deterministic resume

Expose:

```bash
yandex-reaper-experiment resume artifacts/work/<experiment_id>/<run_id>
```

Required recovery semantics:

- [ ] recover by preserved workdir, not by original external manifest path
- [ ] verify `run-state.json`, manifest SHA, workflow version, and path identity before network I/O
- [ ] reuse original `run_id`
- [ ] reuse original `started_at`
- [ ] recreate immutable query-family identity using original `started_at`
- [ ] use **whole exact query** as the search recovery unit
- [ ] reuse only structurally valid `COMPLETED` search runs
- [ ] never reuse `RUNNING`, `PARTIAL`, or `FAILED` runs
- [ ] rerun an interrupted exact query from page 1
- [ ] preserve stale runs as forensic history rather than deleting them
- [ ] add narrow store-level lookup for recovery; coordinator must not depend on ad-hoc raw SQL
- [ ] validate reusable queries through the same raw replay/request/page-chain semantics used by
      comparable construction
- [ ] use existing valid immutable comparable as authoritative first when recovering a family
- [ ] build missing comparable once all exact-query evidence exists
- [ ] fail closed on conflicting immutable comparable state
- [ ] rebuild downstream reports/exports/features instead of creating a generic checkpoint engine
- [ ] recollect rich metadata from the beginning on resume; no rich-batch checkpointing in v1.2

### M1.5.3 — Bounded exact-query workers

Worker contract:

```text
default workers = 4
allowed CLI range = 1..4
unit of concurrency = one exact query
pagination within one query = sequential
```

Required behavior:

- [ ] schedule pending exact queries globally across the manifest
- [ ] allow at most four active exact-query units
- [ ] isolate per-query HTTP/session state
- [ ] never parallelize pages of the same query
- [ ] make manifest order, not completion order, authoritative for comparable/report assembly
- [ ] make the central event/log emitter thread-safe
- [ ] explicitly protect all shared SQLite write paths touched by search workers
- [ ] prefer concurrent network waits + serialized persistence boundary over accidental
      multi-writer SQLite behavior
- [ ] do not reimplement Yandex collection/parsing/storage semantics merely to obtain workers
- [ ] after one terminal query failure, stop scheduling new work
- [ ] allow already-active sibling queries to finish safely
- [ ] preserve valid sibling `COMPLETED` evidence for future resume
- [ ] do not build partial comparables after an incomplete search stage

### M1.5.4 — Artifact/crash safety

- [ ] introduce one explicit final-artifact payload selector shared by artifact-manifest creation
      and ZIP writing
- [ ] exclude recovery-only `run-state.json`, live logs, locks, and temporary package files from
      the final immutable payload
- [ ] tolerate orphan raw directories after hard kill only when they are not bound into valid
      persisted probe evidence
- [ ] freeze deterministic successful-run timing report before packaging
- [ ] build package at an owned temporary path
- [ ] fully verify temporary ZIP before final publication
- [ ] calculate final ZIP hash before/with create-only publication semantics
- [ ] never silently overwrite `artifacts/exports/<experiment_id>/<run_id>.zip`
- [ ] if a verified final artifact already exists after a crash boundary, recognize terminal
      success instead of recollecting/overwriting
- [ ] delete workdir only after verified final artifact success

### M1.5.5 — Verification and release

Focused tests must cover:

```text
run identity
resume identity
completed-query reuse
stale/partial/failed query rerun
raw replay validation
comparable-first recovery
workdir locking
worker bounds
sequential per-query pagination
concurrent failure semantics
SQLite persistence safety
thread-safe logs/events
heartbeat
timings
downstream rebuild
artifact allowlist
crash-safe package publication
```

Release acceptance:

- [ ] existing manifest schema v1 remains accepted
- [ ] existing evidence-honesty/raw-first/provenance contracts remain green
- [ ] `ruff` passes
- [ ] strict `mypy` passes
- [ ] full `pytest` suite passes
- [ ] coverage remains at least 80%
- [ ] package version and `__version__` become `0.2.0` only when all M1.5 capabilities are present
- [ ] run one real instrumented large sweep with `workers=4`
- [ ] prove no storage corruption/source-semantic regression
- [ ] record actual timing evidence instead of claiming an assumed 4× speedup
- [ ] where practical, demonstrate hard-kill → same-workdir resume → verifier PASS

### M1.5 Definition of Done

`0.2.0` is complete only when:

```text
observable execution
+ exact-query recovery
+ bounded four-worker collection
+ deterministic comparable/report assembly
+ crash-safe artifact publication
+ fresh downstream verification
+ real sweep acceptance
```

Explicitly out of scope:

```text
scheduler
daemon
job queue
generic DAG/task framework
distributed workers
generic checkpoint registry
cross-experiment cache
rich-metadata resume
parallel rich metadata
parallel downstream derivation
adaptive worker tuning
proxy rotation / anti-bot evasion
TTY/web dashboard
```

---

## M1.6 — Immediate post-`0.2.0` real opportunity sweep — REQUIRED BEFORE NEW INFRASTRUCTURE

This is an **analysis task**, not a new software platform milestone.

Primary target:

```text
Mystery / Unboxing / Collection sweep
15 families
36 exact queries
3 pages
4 workers
```

Required analyst sequence:

- [ ] run/resume the full sweep through the verified v1.2 runner
- [ ] inspect query-level coherence rather than trusting family labels blindly
- [ ] identify fresh outliers and meaningful supply/traction-proxy asymmetries
- [ ] inspect developer concentration and repeated/reskinned supply
- [ ] inspect descriptions/instructions/screenshots where needed to understand actual gameplay
- [ ] decompose promising games into their true production burden
- [ ] explicitly score/describe reward strength and re-themeability
- [ ] separate clone graveyards from genuine low-burden asymmetric opportunities
- [ ] produce **1–3 concrete ultra-simple candidate theses**
- [ ] assign provisional `BUILD / WATCH / SKIP` judgment manually
- [ ] choose at least one candidate worth routing into M2

Primary analytical question:

> Can we find an ultra-low-production-burden game whose simple action → expectation → visual/reward
> loop has a plausible path to disproportionate live traffic and a long advertising tail?

Do not start M3 discovery automation or another runner/platform redesign instead of completing this
sweep.

---

## M2 — Candidate Dossier v0 — `FIRST DECISION LOOP`

Goal: turn human-selected market hypotheses into explicit, inspectable decisions without pretending
the policy has been historically validated.

**Sequencing rule:** M2 implementation begins from a real candidate produced by M1.6. Do not build
the dossier in a vacuum before the post-`0.2.0` sweep yields a concrete thesis.

### M2.1 — Candidate identity and evidence package

- [ ] candidate concept versioning
- [ ] bind each candidate to exact analyst snapshot/comparable-set versions
- [ ] preserve supporting evidence, counter-evidence, unknowns, and evidence coverage
- [ ] make derived market features traceable to source observations/raw evidence

### M2.2 — Production assessment

- [ ] freeze v1 rubrics for dev complexity, assets, content, backend, balancing, liveops, QA,
      mobile adaptation, and AI-assisted fit
- [ ] implement candidate-specific production-assessment workflow
- [ ] store estimated MVP day range, major risks, reusable systems, tooling profile, and version
- [ ] keep production feasibility separate from market taxonomy
- [ ] strongly weight production burden: an attractive market does not justify a complex game

### M2.3 — Heuristic market prior + decision policy

- [ ] implement decomposable current-market prior inputs from M1 features
- [ ] implement evidence-coverage calculation
- [ ] implement provisional BUILD / WATCH / SKIP policy
- [ ] label every pre-backtest decision `heuristic`
- [ ] require rationale, counter-evidence, unknowns, and WATCH/SKIP follow-up conditions
- [ ] do not introduce an opaque opportunity score

### M2.4 — Dossier artifact

- [ ] generate one stable human-readable candidate dossier artifact
- [ ] include thesis, comparable set, market evidence, production assessment, evidence coverage,
      decision, and raw/normalized evidence references
- [ ] freeze a pre-build dossier/decision snapshot so later outcomes cannot rewrite the thesis

### M2.5 — First real decision loop

- [ ] run at least one M1.6 candidate through the complete dossier flow
- [ ] independently review whether another analyst can reconstruct the decision
- [ ] fix usability/evidence gaps exposed by the real dossier

### `FIRST DECISION LOOP` gate

```text
real current-market evidence
→ concrete candidate
→ comparable analysis
→ production assessment
→ evidence coverage
→ dossier
→ heuristic BUILD / WATCH / SKIP
```

Backtesting later determines whether the heuristic policy deserves stronger validation status.

---

## M3 — Yandex-native opportunity discovery v0

Goal: reduce manual idea generation only after M1.6/M2 demonstrate that the underlying evidence
and candidate decision loop are useful.

- [ ] aggregate Yandex-native supply/quality/traction-proxy features across eligible market seeds
- [ ] add transparent/versioned discovery heuristics
- [ ] surface candidate seeds with explicit `why surfaced`
- [ ] dedupe candidate concepts / obvious repeated hypotheses
- [ ] apply production feasibility after market-seed generation, not inside taxonomy
- [ ] preserve source feature snapshot/version for every surfaced candidate
- [ ] feed surfaced candidates into M2
- [ ] keep discovery results heuristic until historical evaluation exists

A validated taxonomy/classifier improves scale and consistency. Until it lands, taxonomy-driven
automatic discovery remains provisional or analyst-reviewed. Query-family exploration continues
independently.

**Definition of Done:** the system can surface plausible Yandex-native candidate hypotheses and
route them into the proven dossier loop.

---

# PARALLEL EVIDENCE / VALIDATION TRACKS

These tracks increase confidence and eventually replace provisional collection/taxonomy
assumptions. They do not block the current on-demand analysis path unless a specific feature would
otherwise consume an unfinished conclusion.

## V1 — Market-collection calibration

### Feed depth

- [x] freeze `feed-depth-v1` protocol and replay/analyzer tooling
- [ ] execute empirical calibration with frozen minimum sample/time-span guards
- [ ] record resulting depth decision
- [ ] replace analyst collection parameters only via explicit versioned operating-profile change

### Session profile

- [x] freeze `session-profile-stability-v1` protocol and matched-block replay/analyzer tooling
- [ ] execute empirical matched-block calibration with frozen sample/time/order guards
- [ ] record per-depth classifications
- [ ] change analyst/production session policy only if real evidence supports it

### Collection cadence

- [x] freeze `collection-cadence-v1` protocol
- [x] merge immutable pre-collection plan + raw-first reference/downsampling replay tooling
- [ ] execute at least 28 consecutive daily reference checkpoints
- [ ] record capability/depth cadence decisions
- [ ] introduce scheduled production collection only after cadence policy is explicit

The 28-day cadence experiment is calendar-bound and must not delay current on-demand analysis.

## V2 — Taxonomy validation and classifier

### Existing tooling

- [x] pragmatic primary archetype + controlled-dimensions model
- [x] `unknown` distinct from `other`
- [x] controlled registries for mechanics/objectives/meta/tone
- [x] `taxonomy-diversity-sample-v1` deterministic sampler
- [x] manual annotation/adjudication contracts and gold-set tooling
- [x] primary-archetype validation/review tooling
- [x] primary independent-annotation agreement/confusion tooling
- [x] controlled-dimension exact-set agreement + per-label gold-alignment tooling

### Still required

- [ ] freeze theme-canonicalization validation protocol/tooling
- [ ] execute sampler against real Yandex evidence and freeze 100–200-listing sample identity/hash
- [ ] execute genuine independent annotation/adjudication and freeze gold-set identity/hash
- [ ] execute primary-archetype review
- [ ] execute real primary agreement/confusion analysis
- [ ] execute real controlled-dimension agreement analysis
- [ ] execute real theme-canonicalization analysis
- [ ] revise taxonomy from empirical evidence
- [ ] freeze first validated taxonomy version
- [ ] implement classifier only after schema stabilizes
- [ ] build taxonomy-refined comparable construction as a new explicit construction version

**Definition of Done:** automated taxonomy use is consistent enough for scalable market
aggregation; low-confidence cases remain explicitly unknown.

---

# POST-USEFUL-LOOP VALIDATION AND SCALE

## M4 — Unattended / scheduled collection automation

This milestone no longer owns basic query-family batch execution or interactive runner
retry/recovery: those belong to the already-existing analyst runner and M1.5.

M4 begins only when repeated analysis demonstrates a real need for unattended collection.

- [ ] schedule repeated runs using the empirically selected cadence
- [ ] define unattended process supervision / job ownership
- [ ] define unattended notification/reporting for failed or completed scheduled runs
- [ ] reuse v1.2 run identity, resume, observability, artifact, and evidence boundaries
- [ ] add authenticated-test credential/profile provider only if a concrete analysis needs it
- [ ] define safe scheduled retry/resume policy without changing evidence cohorts silently
- [ ] preserve raw-first, context, lineage, and schema-drift guarantees

A dashboard remains optional. Build one only if repeated analyst use shows that CLI/JSON/CSV
artifacts materially slow the workflow.

---

## M5 — Historical backfill

- [ ] import available historical sources
- [ ] record source timezone, data lag, revision policy, and `available_at` semantics
- [ ] distinguish historical availability from revision/recalculation status
- [ ] validate strict point-in-time eligibility
- [ ] model platform-policy regimes
- [ ] add failure reason/censoring support
- [ ] add near-duplicate/template-family metadata where feasible

**Definition of Done:** historical observations clearly declare whether they can be used in strict
point-in-time analysis.

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
- [ ] promote decision policy status from `heuristic` only if evidence supports it

**Definition of Done:** recommended candidates beat simple baselines on an untouched temporal
holdout without known time/data leakage.

---

## M7 — External trend enrichment

- [ ] Wordstat
- [ ] YouTube
- [ ] TGStat
- [ ] Google Trends if available
- [ ] optional cross-market sources
- [ ] measure whether each external signal improves candidate discovery/decisions

External trends enrich the proven Yandex-native loop; they are not prerequisites for the first
dossier.

---

## M8 — Own-game calibration

- [ ] freeze immutable pre-build prediction/dossier snapshot for each release
- [ ] capture actual development cost
- [ ] import actual Yandex analytics/revenue
- [ ] append realized outcome cohorts after every release
- [ ] run periodic versioned production/decision calibration reviews
- [ ] personalize production estimates and decision thresholds

Do not silently update thresholds after every release. Each calibration change creates a new
explicit assessment/policy version.

---

# Current sequencing guard

Until M1.5 / Reaper `0.2.0` is complete, reject work that does not materially improve at least one
of:

```text
run identity / crash safety
live observability
deterministic exact-query resume
bounded exact-query concurrency
storage safety under concurrency
deterministic artifact assembly
verified artifact publication
```

After `0.2.0`, the next mandatory work is M1.6 — the real Mystery / Unboxing / Collection analysis.
Do not substitute:

```text
another runner redesign
scheduler
dashboard
generic orchestration framework
taxonomy expansion
ML/ranking
broad external-source integration
```

for that sweep.

Before `FIRST DECISION LOOP`, work should materially improve:

```text
real candidate evidence
production assessment
evidence coverage
dossier usability
explicit heuristic decision-making
```

The project optimizes for finding and testing **simple asymmetric opportunities**, not for
maximizing architectural sophistication.
