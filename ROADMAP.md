# Roadmap

`ROADMAP.md` is the sequencing source of truth for the active Yandex Analytics Reaper delivery path.
The detailed pre-`0.2.0` roadmap is preserved verbatim at
[`docs/history/ROADMAP-pre-0.2.0.md`](docs/history/ROADMAP-pre-0.2.0.md).

The project optimizes for **time to evidence-backed low-production opportunities**, not for
infrastructure sophistication.

## Evidence rules

- raw/current evidence and provenance remain authoritative;
- `ratingCount`, search exposure/rank and query supply are proxies, not DAU, revenue, retention,
  CTR, playtime or profitability;
- manual/heuristic decisions must be labeled as such;
- query-family coherence must be inspected before treating a family as one market;
- production burden is a first-class decision variable;
- no new infrastructure milestone may replace a concrete market/build decision loop.

## Delivery paths

The product-validation lane and research-tool lane may move independently. Tooling work must not
silently reopen or displace an accepted production decision.

```text
RESEARCH-TOOL LANE
M0 evidence foundation — COMPLETE
-> M1 analyst workbench / START ANALYSIS — COMPLETE
-> M1.5 Reaper 0.2.0 / Runner v1.2 — COMPLETE
-> M1.6 Mystery / Unboxing / Collection sweep — COMPLETE
-> M1.7 semantic/directness triage — COMPLETE
-> R0.3 Reaper 0.3.0 / Thesis Intelligence — COMPLETE
-> R0.3.1 durable evidence archive — COMPLETE
-> R0.4 evidence completeness / data quality — ACTIVE; P1 NEXT

PRODUCT-VALIDATION LANE
M2 candidate dossier / FIRST DECISION LOOP — COMPLETE
-> P1 production-ready micro-spec — COMPLETE
-> P2 cheapest credible build/release probe — NEXT PRIMARY PRODUCT PATH
-> observe real behavior
-> calibrate, re-theme or kill the thesis
```

---

## M0 — Trustworthy evidence foundation — COMPLETE

The system can collect, replay, normalize, persist and trace Yandex evidence without silently
collapsing source uncertainty.

Historical detail:
[`docs/history/ROADMAP-pre-0.2.0.md`](docs/history/ROADMAP-pre-0.2.0.md).

## M1 — Analyst Workbench v0 / `START ANALYSIS` — COMPLETE 2026-08-30

Human-in-the-loop analysis can collect real evidence, declare explicit query families, build
reproducible comparables, inspect supply/traction proxies and trace results back to provenance.

Evidence:
[`docs/history/analyst-pilot-2026-08-30.md`](docs/history/analyst-pilot-2026-08-30.md).

## M1.5 — Reaper `0.2.0` / Analyst Experiment Runner v1.2 — COMPLETE 2026-09-01

Delivered and accepted:

- immutable run identity + manifest hash;
- exclusive workdir locking;
- progress logs/events + heartbeat;
- deterministic same-workdir resume;
- completed-query reuse and stale interrupted-run rejection;
- comparable-first recovery;
- bounded `1..4` exact-query workers, default `4`;
- sequential pagination within each query;
- isolated query sessions;
- serialized SQLite-affecting persistence;
- deterministic manifest-order assembly;
- crash-safe verified create-only artifact publication;
- final timing/reuse metadata;
- package version `0.2.0`.

Real acceptance used 15 families / 36 exact queries / 3 pages, deliberately hard-killed the first
invocation, resumed the same workdir with four workers, reused four valid completed queries,
collected 32, finished 36/36 and produced verifier PASS.

Evidence:
[`docs/history/reaper-0.2.0-acceptance-2026-09-01.md`](docs/history/reaper-0.2.0-acceptance-2026-09-01.md).

No runner redesign, scheduler, daemon, generic DAG, distributed worker layer, dashboard, generic
checkpoint framework or cache layer is currently justified.

## M1.6 — Mystery / Unboxing / Collection opportunity sweep — COMPLETE 2026-09-01

Collection:

```text
15 analyst families
36 exact queries
3 pages
clean anonymous RU desktop
665 unique listings
665 / 665 rich metadata
```

Research:
[`research/mystery-unboxing-collection-sweep-v1/`](research/mystery-unboxing-collection-sweep-v1/).

### M1.6 decisions

**BUILD / route to M2:** `tactile-mystery-collectibles-v1`.

Current corrected grammar:

```text
original mystery package
-> one short deterministic pointer/touch interaction
-> anticipation
-> random collectible + obvious rarity
-> album / duplicate currency
-> next package
```

Direct inspection of primary reference listing `533677` superseded the earlier speculative
2–4-action tactile sequence.

**WATCH:** `simplified-lucky-object-reveal-v1`.

**SKIP:** generic real-object case simulator, low-effort pack-opening reskin factory,
Standoff/Brawl/IP case clone, and full 3D lucky-block/brainrot clone.

Rationale:
[`research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`](research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md).

## M1.7 — Semantic / directness triage — COMPLETE 2026-09-02

Later thesis-oriented sweeps exposed a repeated operational bottleneck: Yandex search is fuzzy
enough that a large search union can contain many semantically irrelevant listings, while the rich
metadata path already stores description/instruction/category/tag evidence that is not surfaced in
the analyst export.

M1.7 is a **narrow bottleneck fix**, not a return to broad taxonomy work.

Scope:

```text
frozen AnalystSnapshotReport
+ versioned mechanic × theme thesis terms
+ existing catalogue.get_games raw metadata
-> reproducible semantic corpus
-> theme/mechanic/reward lexical evidence
-> direct_candidate / adjacent_candidate / noise_candidate / insufficient_evidence
-> evidence snippets + raw provenance
```

Constraints:

- no new Yandex endpoint or broad collection source;
- no embeddings/LLM/API dependency;
- no opaque opportunity/directness score;
- no claim that lexical `direct_candidate` is a confirmed gameplay competitor;
- no rewrite of comparable-set v1 or historical taxonomy;
- no SQLite/domain schema migration solely to carry source-specific descriptive text;
- the artifact must replay frozen raw evidence and remain hash-verifiable;
- P2 remains the next primary product path.

Specification:
[`docs/spec/analyst-semantic-enrichment.md`](docs/spec/analyst-semantic-enrichment.md).

Real-data validation:
[`research/semantic-directness-v1/validation-2026-09-02.md`](research/semantic-directness-v1/validation-2026-09-02.md).

The frozen V3 `custom-headphones` set demonstrated the intended operational gain:

```text
312 fuzzy listings
-> 243 noise_candidate
-> 67 adjacent_candidate
-> 2 direct_candidate
-> 0 meaningful direct matches after contextual review of frozen descriptions/instructions
```

This is review-queue reduction, not a market-size or absolute-absence claim.

Definition of Done:

- [x] versioned semantic thesis declaration;
- [x] frozen `get_games` semantic corpus replay;
- [x] transparent dimension matching + evidence snippets;
- [x] conservative candidate-level directness labels;
- [x] deterministic JSON report + analyst-readable CSV;
- [x] CLI entry point;
- [x] focused replay/classification tests pass in CI;
- [x] full repository quality gate passes;
- [x] one real thesis artifact demonstrates useful reduction of fuzzy search noise;
- [x] decision methodology is synchronized with the shipped contract.

---

# R0.3 — Reaper `0.3.0` / Thesis Intelligence — COMPLETE 2026-09-02

Purpose:

> Turn several explicit `mechanic x theme/object` theses into compact, comparable, reproducible
> evidence packages while preserving the existing human decision boundary.

Full product/semantic plan:
[`docs/spec/thesis-intelligence.md`](docs/spec/thesis-intelligence.md).

0.3 approved scope is limited to:

1. thesis-suite declaration and deterministic compilation onto existing experiment semantics;
2. age-normalized traction plus real rating deltas only from explicitly bound frozen prior experiment artifacts;
3. explicit-policy fresh anomaly review queue;
4. hash-bound analyst directness review plus competitor-set quality summary;
5. deterministic cross-thesis JSON/CSV/Markdown comparison;
6. thin `run/build/verify` coordination that reuses the 0.2 runner rather than replacing it.

## R0.3 sequencing

```text
0.3-P0 contract freeze — COMPLETE
-> 0.3-P1 thesis-suite compiler + artifact bindings — COMPLETE
-> 0.3-P2 traction features + frozen prior-artifact delta support — COMPLETE
-> 0.3-P3 fresh anomaly queue — COMPLETE
-> 0.3-P4 directness review + competitor quality — COMPLETE
-> 0.3-P5 cross-thesis comparison — COMPLETE
-> 0.3-P6 thin CLI integration — COMPLETE
-> 0.3-P7 V3 replay + Satisfying Destruction live validation — COMPLETE
-> package/release 0.3.0 — COMPLETE
```

### 0.3-P0 — Contract freeze — COMPLETE 2026-09-02

Before implementation:

- [x] freeze exact `thesis-suite-v1` schema;
- [x] freeze current/prior experiment artifact binding schema and deterministic history selection rules;
- [x] freeze age-bucket boundary semantics;
- [x] freeze too-young lifetime-pace behavior;
- [x] freeze anomaly gate pass/fail/unknown semantics;
- [x] freeze analyst directness review schema and verdict vocabulary;
- [x] freeze per-thesis report schema;
- [x] freeze cross-thesis comparison schema;
- [x] independently review the spec for measurement honesty and unnecessary infrastructure.

### 0.3-P1 — Thesis suite compiler + artifact bindings — COMPLETE 2026-09-02

- [x] map each thesis deterministically to one existing query-family/comparable identity;
- [x] compile the suite to the current experiment manifest semantics without changing search behavior;
- [x] compile M1.7 semantic declarations deterministically;
- [x] bind the exact immutable current experiment artifact by hash;
- [x] support an ordered set of optional prior experiment artifact hashes for longitudinal evidence;
- [x] add create-only thesis-intelligence artifact identity/verification primitives;
- [x] preserve exact thesis/query declaration order.

### 0.3-P2 — Traction features — COMPLETE 2026-09-02

- [x] derive first-publication age from frozen snapshot time;
- [x] derive versioned age buckets;
- [x] expose `ratingCount` coverage separately from numeric values;
- [x] derive lifetime ratings/day only when method prerequisites are met;
- [x] derive suite-relative age-bucket cohort percentile with cohort definition/size;
- [x] verify/read `rating_count` observations from explicitly supplied prior experiment artifacts;
- [x] select the latest eligible prior point deterministically and bind its artifact/observation identity;
- [x] expose observed rating delta/day only when two trustworthy frozen observations exist;
- [x] preserve negative deltas/revision states rather than clamping;
- [x] never consult ambient mutable local SQLite state during deterministic `build`;
- [x] no schema migration unless a separate measured requirement later proves one necessary.

### 0.3-P3 — Fresh anomaly queue — COMPLETE 2026-09-02

- [x] require explicit anomaly thresholds in analyst input;
- [x] emit traceable per-gate `pass / fail / unknown / not_configured` states;
- [x] treat missing configured evidence as unknown/fail according to the frozen contract, never as zero;
- [x] permit a longitudinal velocity gate only against bound prior-artifact evidence;
- [x] deterministic queue ordering without opportunity score;
- [x] preserve the distinction between anomaly candidate and successful game.

### 0.3-P4 — Directness review + competitor quality — COMPLETE 2026-09-02

- [x] create hash-bound analyst review artifact;
- [x] support `confirmed_direct / adjacent / not_direct / unresolved`;
- [x] calculate review coverage and false-positive counts;
- [x] summarize raw union vs semantic direct/adjacent/noise/insufficient counts;
- [x] summarize per-query contribution and overlap/Jaccard descriptors;
- [x] expose bounded zero-confirmed state without claiming absolute market absence.

Review:
[`docs/history/reaper-0.3-p4-review-2026-09-02.md`](docs/history/reaper-0.3-p4-review-2026-09-02.md).

### 0.3-P5 — Cross-thesis comparison — COMPLETE 2026-09-02

- [x] stable declaration-order rows;
- [x] direct evidence never silently replaced with adjacent evidence;
- [x] expose confirmed direct/fresh direct/anomaly/coverage/query-quality facts;
- [x] expose longitudinal coverage only for explicitly bound prior artifacts;
- [x] include listing IDs/provenance with best-traction facts;
- [x] emit canonical JSON plus analyst-readable CSV/Markdown;
- [x] no automatic winner or BUILD/WATCH/SKIP.

Review:
[`docs/history/reaper-0.3-p5-review-2026-09-02.md`](docs/history/reaper-0.3-p5-review-2026-09-02.md).

### 0.3-P6 — CLI integration — COMPLETE 2026-09-02

- [x] `yandex-reaper-thesis run` delegates current collection to existing experiment runner;
- [x] `run/build` accept optional repeatable prior experiment artifact inputs;
- [x] collection failure surfaces the existing resume path;
- [x] `build` reconstructs intelligence from verified frozen current/prior artifacts without network access;
- [x] `build` can add hash-bound analyst review artifacts without recollecting Yandex data;
- [x] `verify` checks package members/hashes and performs a source-bound deterministic rebuild;
- [x] prior artifact inputs canonicalize independently of CLI argument order;
- [x] final create-only identity includes `build_input_hash` so review-only rebuilds cannot collide;
- [x] post-processing failure cannot mutate any source experiment artifact.

Review:
[`docs/history/reaper-0.3-p6-review-2026-09-02.md`](docs/history/reaper-0.3-p6-review-2026-09-02.md).

P4 review artifacts are intentionally accepted by offline `build`, not by fresh `run`: a review
binds an already-existing semantic-report hash, so the honest workflow is `run -> inspect -> review
-> build same current ZIP` without recollecting Yandex data.

### 0.3-P7 — Real-data validation + release — COMPLETE 2026-09-02

Replay existing V3 evidence where possible:

- [x] Custom Headphones — fuzzy-noise / zero-confirmed-direct control;
- [x] Custom Digicam — weak-direct-supply control;
- [x] Restore Retro Tech — near-direct/adjacent control.

Run one new focused thesis sweep:

- [x] Satisfying Destruction — broader direct grammar exists, but the recent signal is concentrated in one strong fresh breakout.

Longitudinal validation:

- [x] zero-history build correctly reports no prior observation rather than fake velocity;
- [x] bind prior experiment artifacts in deterministic fixtures and verify positive/negative/no-change delta handling.

Release gate:

- [x] real validation demonstrates material manual-review reduction;
- [x] comparison output is manually reviewed for measurement honesty;
- [x] existing 0.2 runner acceptance behavior remains intact;
- [x] `ruff`, strict `mypy`, full `pytest` and repository coverage gate pass;
- [x] methodology/decision docs are synchronized with the bounded P7 conclusions;
- [x] authoritative package version/provenance is `0.3.0` after the release gates passed.

Validation evidence:
[`docs/history/reaper-0.3-p7-validation-2026-09-02.md`](docs/history/reaper-0.3-p7-validation-2026-09-02.md).

## R0.3 explicit non-goals

Do not add during 0.3:

```text
LLM / embeddings / vector DB
opaque opportunity score
automatic BUILD / WATCH / SKIP
automatic production-burden estimation
visual screenshot classifier
query-generation / uncontrolled synonym expansion
external trend ingestion
additional game platforms
scheduler / daemon / monitoring service
dashboard / web UI
distributed workers
new generic workflow framework
broad taxonomy redesign
market-size estimation
ambient mutable local-DB history during deterministic build
fabricated 7d/30d/90d velocity without repeated frozen observations
```

Potential `0.3.1+` work such as controlled query expansion, cross-thesis reuse diagnostics, and
sweep-to-sweep change detection must be justified by real 0.3 usage rather than pulled into the
release preemptively.

---

# R0.3.1 — Durable evidence archive — COMPLETE 2026-09-14

Real 0.3 usage exposed one bounded infrastructure defect: longitudinal analysis deliberately binds
old immutable experiment artifacts, while the September trend-sweep copies existed only as
30-day GitHub Actions artifacts. Expiration would destroy replayable source evidence even though
0.3's delta semantics were otherwise correct.

This correction is intentionally narrower than a storage platform:

```text
committed expected artifact provenance + SHA/size
-> exact Actions artifact ZIP download
-> deterministic wrapper/member hash manifest
-> create-only GitHub Release publication
-> verified later extraction of exact inner experiment ZIP
-> unchanged existing --prior longitudinal path
```

Specification:
[`docs/spec/durable-evidence-archive.md`](docs/spec/durable-evidence-archive.md).

Initial request catalog:
[`research/archive/`](research/archive/).

Live migration acceptance:
[`docs/history/durable-evidence-archive-live-migration-2026-09-14.md`](docs/history/durable-evidence-archive-live-migration-2026-09-14.md).

Implementation gate:

- [x] preserve the exact Actions wrapper ZIP bytes rather than repacking them;
- [x] fail closed unless downloaded SHA-256 and size equal the committed request;
- [x] inventory every non-directory inner member by exact path, size and SHA-256;
- [x] reject unsafe/duplicate ZIP member paths;
- [x] support offline wrapper verification and hash-checked inner-member extraction;
- [x] keep GitHub transport outside the offline archive core;
- [x] use draft-first, create-only Release reconciliation with no clobber path;
- [x] keep heavy evidence out of normal Git history;
- [x] declare the four Sep-13 round-2..5 artifacts before their 2026-10-13 expiry;
- [x] full repository quality gate passes on the implementation PR;
- [x] implementation/spec receive independent review and any findings are repaired;
- [x] all four historical requests are published to durable Releases and re-downloaded/verified;
- [x] final live migration review is recorded and this milestone is marked COMPLETE.

Live publication completed on 2026-09-14 in GitHub Actions run `34828794788`. All four wrappers, manifests and checksums were redownloaded and verified before publication. GitHub currently reports `immutable = false` for the Releases, so repository-level immutable releases are not assumed; create-only/no-clobber behavior and cryptographic verification remain the evidence-integrity boundary.

This work does **not** reopen product sequencing. `P2` remains the next primary product path, and a
scheduler, object-storage abstraction, remote-history database or generic artifact platform remain
out of scope.

---

# R0.4 — Evidence completeness / data quality — ACTIVE 2026-09-14

Real post-0.3 usage exposed a different class of evidence defect than durable storage:

- a known direct listing can exist outside the bounded search surface, so exact-ID evidence must not depend on rediscovery;
- repeated observations of known competitors should not require repeating a whole search experiment;
- external/manual evidence used in decisions needs explicit provenance and durable hash binding;
- search-derived, point-observed and supplemental evidence must never be silently flattened into one market-supply claim.

Normative semantics:
[`docs/spec/evidence-completeness-v1.md`](docs/spec/evidence-completeness-v1.md).

Independent plan review:
[`docs/history/reaper-r0.4-plan-review-2026-09-14.md`](docs/history/reaper-r0.4-plan-review-2026-09-14.md).

The review removed a proposed duplicate rich-metadata layer because the current experiment runner and `YandexRichMetadataCollector` already provide raw-first `get_games` enrichment. It also rejects query expansion as a guaranteed recall fix, defers scheduling until the observation artifact is accepted, and keeps visual/review judgments as labeled analyst evidence rather than automatic scores.

## R0.4 sequencing

```text
R0.4-P0 contract freeze + independent review — COMPLETE
-> R0.4-P1 exact-ID point observation artifact — NEXT
-> R0.4-P2 known-ID longitudinal comparison
-> R0.4-P3 supplemental evidence bundle
-> R0.4-P4 thesis evidence-pack integration
-> R0.4-P5 real-data validation
-> optional scheduled watch only after artifact acceptance
```

### R0.4-P0 — Contract freeze + review — COMPLETE 2026-09-14

- [x] separate `search_discovered`, `point_observed`, `supplemental_attached` and weaker `reference_only` provenance;
- [x] preserve frozen 0.3 Thesis Intelligence/build-identity contracts unchanged;
- [x] define exact-ID requested/returned/missing/unexpected semantics;
- [x] require self-contained hash-bound point-observation artifacts with offline replay verification;
- [x] define real longitudinal delta only from repeated frozen observations;
- [x] define supplemental external/manual evidence with attachment SHA/size identity;
- [x] keep human qualitative judgments explicitly analyst-owned;
- [x] independently review for duplicate collection paths, measurement overclaim and infrastructure scope creep.

### R0.4-P1 — Exact-ID point observation artifact — NEXT

Reuse the existing `YandexRichMetadataCollector` and `catalogue.get_games` path.

Definition of Done:

- [ ] versioned `listing-observation-set-v1` declaration with unique ordered app IDs;
- [ ] raw-first exact-ID collection through the existing Yandex client/collector;
- [ ] explicit requested / returned / missing / unexpected ID accounting;
- [ ] deterministic create-only artifact with declaration, observation, exact raw bytes and member manifest;
- [ ] offline verifier reparses raw evidence and reconstructs observation identity/facts;
- [ ] no search/query membership is invented for point-observed IDs;
- [ ] CLI entry point and focused tests;
- [ ] full `ruff`, strict `mypy`, `pytest`/coverage gate passes;
- [ ] live Keycap control observes `540402`, `559445`, `553722` without modifying the historical search union;
- [ ] implementation receives independent diff/code review before merge.

### R0.4-P2 — Known-ID longitudinal comparison

- [ ] compare compatible point-observation artifacts for an explicit cohort;
- [ ] derive rating-count delta/day only across actual frozen observations;
- [ ] preserve missing values and negative/revision deltas;
- [ ] expose elapsed interval and exact artifact/source identity;
- [ ] keep point velocity distinct from search visibility and lifetime pace;
- [ ] validate with a second real Keycap observation after a meaningful interval.

### R0.4-P3 — Supplemental evidence bundle

- [ ] versioned analyst-owned bundle for external/manual evidence;
- [ ] bind thesis/listing target, source kind/reference, observation time, claim/measurement and confidence;
- [ ] hash attached bytes by exact SHA-256/size;
- [ ] mark URL-only evidence as `reference_only` rather than immutable proof;
- [ ] support typed human visual/review-contamination annotations without automatic scoring;
- [ ] validate against one real external-evidence thesis package.

### R0.4-P4 — Thesis evidence pack integration

- [ ] introduce additive `thesis-evidence-pack-v1` rather than mutate 0.3 v1 build inputs;
- [ ] bind one verified Thesis Intelligence artifact plus optional point/supplemental artifacts;
- [ ] preserve channel-specific provenance/counts in compact JSON/Markdown output;
- [ ] point-observed listings never inflate search-union supply/direct-search counts;
- [ ] evidence pack remains deterministic/hash-verifiable and makes no automatic portfolio decision.

### R0.4-P5 — Real-data validation

- [ ] Keycap proves exact known-ID coverage outside search recall;
- [ ] Decorated Mail proves external supplemental evidence remains external rather than Yandex demand proof;
- [ ] one repeated Keycap observation proves real longitudinal delta semantics;
- [ ] final review confirms manual evidence loss is materially reduced without creating a generic data platform.

## R0.4 explicit non-goals

```text
second Yandex rich-metadata collector
uncontrolled query expansion
automatic competitor truth
generic web crawler
app-store/trend connectors before the manual bundle proves the contract useful
visual ML / LLM classifier
generic scheduler / daemon in P0-P5
cross-platform entity-resolution engine
dashboard / opportunity score / automatic BUILD-WATCH-SKIP
```

R0.4 is a research-tool lane improvement only. It may proceed in parallel with product work and must not silently reorder the production queue.

---

# M2 / FIRST DECISION LOOP — COMPLETE 2026-09-01

Candidate directory:
[`research/candidates/tactile-mystery-collectibles-v1/`](research/candidates/tactile-mystery-collectibles-v1/).

Current decision version: **v2**.

```text
decision: BUILD
scope: small_probe
market_prior: favorable
production_fit: strong
evidence_coverage: medium
decision_validation_status: heuristic
estimated_mvp_days: 4.5–6.5 focused person-days
```

Completed:

- [x] versioned candidate identity;
- [x] exact sweep/run binding;
- [x] supporting evidence, counter-evidence and unknowns;
- [x] claim-by-claim reconstruction path;
- [x] primary reference + negative controls;
- [x] candidate-specific production rubric;
- [x] frozen production estimate and kill conditions;
- [x] visual/public-page correction from candidate v1 -> v2;
- [x] heuristic BUILD/WATCH/SKIP decision;
- [x] superseded v1 artifacts retained as audit history.

Current artifacts:

- [`candidate-v2.json`](research/candidates/tactile-mystery-collectibles-v1/candidate-v2.json)
- [`dossier-v2.md`](research/candidates/tactile-mystery-collectibles-v1/dossier-v2.md)
- [`decision-v2.json`](research/candidates/tactile-mystery-collectibles-v1/decision-v2.json)
- [`evidence-index-v2.md`](research/candidates/tactile-mystery-collectibles-v1/evidence-index-v2.md)

### `FIRST DECISION LOOP` gate — REACHED 2026-09-01

```text
candidate identity
-> exact evidence package
-> production assessment
-> heuristic market prior
-> explicit counter-evidence
-> BUILD / WATCH / SKIP
```

The result is a **BUILD — small probe**, not a profitability claim.

---

# PRIMARY PRODUCT PATH — BUILD PROBE

## P1 — Production-ready micro-spec — COMPLETE 2026-09-01

Frozen implementation artifacts:

- [`implementation-spec-v1.md`](research/candidates/tactile-mystery-collectibles-v1/implementation-spec-v1.md)
- [`probe-config-v1.json`](research/candidates/tactile-mystery-collectibles-v1/probe-config-v1.json)
- [`implementation-review-v1.md`](research/candidates/tactile-mystery-collectibles-v1/implementation-review-v1.md)

The implementation contract freezes:

```text
24 original collectibles
4 rarities
3 package tiers
Paper Pouch always free
one soft currency
one deterministic pull-tab interaction
transactional pendingReveal save
one optional rewarded +20 acceleration point
no manual fullscreen interstitial in the first probe
Yandex safe storage
Yandex loading/gameplay/pause-resume boundaries
12 custom Metrica funnel goals
mouse + touch + keyboard
<=7 focused-day hard kill boundary
```

Independent implementation-readiness review: **PASS**.

Mandatory before producing all 24 final assets: integrate a four-item representative asset spike
(common/rare/epic/legendary) into the actual reveal UI and verify that the production method scales
inside the frozen art/time budget.

## P2 — Cheapest credible build/release probe — NEXT

Start only in a concrete game repository/worktree. Do not put the game implementation inside the
Reaper research codebase.

Recommended stack remains deliberately small:

```text
Vite
React
TypeScript strict
plain CSS/CSS modules
useReducer + pure domain functions
Yandex Games SDK adapter
Yandex Metrica adapter
Vitest domain tests
```

The first behavioral question is:

> After one reveal, do real players voluntarily initiate another package and continue filling the
> collection?

Pre-build stop conditions:

- credible plan exceeds 7 focused person-days;
- 4-item asset spike cannot establish one coherent original family cheaply;
- implementation needs physics/3D/complex bespoke animation;
- reveal is not satisfying without adding a second gameplay system;
- creative requires recognizable third-party IP.

If the released loop is weak, do not rescue it by adding a heavy meta game. Re-theme or kill the
hypothesis according to the frozen M2 conditions.

---

# Deferred beyond accepted 0.3 / product validation work

Potential later work remains valid but is not automatically next:

- broad taxonomy validation/classification beyond the narrow semantic/directness contracts;
- historical backtesting beyond the bounded 0.3 metric-delta use case;
- external trend-source integration;
- portfolio calibration;
- dashboards/scheduling;
- automated ranking;
- multi-platform collection.

Promote any of these only when a real decision/build loop exposes a concrete bottleneck they solve.

## Current sequencing guard

Even with 0.3 approved, reject work whose main effect is:

```text
another runner redesign
scheduler
dashboard
generic orchestration framework
ML/ranking
broad external-source integration
extra gameplay/meta systems inside Reaper
```

0.3 is justified only because repeated real thesis research exposed concrete manual analysis costs.
It must remain a thin evidence/intelligence layer over the proven collector and must not become a
separate platform-analytics product.

The primary product job is still to test whether a **very cheap, original, reward-first collectible
opener** can produce repeat-opening behavior with real Yandex traffic.
