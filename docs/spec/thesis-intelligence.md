# Reaper 0.3.0 — Thesis Intelligence

## Status

**Release:** `0.3.0`  
**Codename:** Thesis Intelligence  
**Planning status:** APPROVED SCOPE / implementation not started  
**Primary objective:** reduce the manual work between a focused Yandex Games thesis sweep and an evidence-backed project decision without turning Reaper into an automatic decision engine.

This release is intentionally built on the already-proven Reaper `0.2.0` experiment runner and the shipped M1.7 semantic/directness triage. It does not redesign collection, recovery, worker scheduling, source parsing, or the evidence model unless a concrete 0.3 requirement cannot be met through an additive read/analyst layer.

---

# 1. Problem statement

Recent real research established five recurring bottlenecks.

## 1.1 Thesis sweeps are still assembled manually

The useful research unit is usually:

```text
mechanic x theme/object
```

Examples:

```text
customization x headphones
customization x digicam
restoration x retro pocket tech
destruction x ordinary objects
```

The current runner can collect query families and produce frozen market artifacts, and M1.7 can reduce fuzzy search noise with semantic/directness triage, but the analyst still has to connect those stages manually.

0.3 should make a thesis a first-class analyst workflow without changing the underlying collection semantics.

## 1.2 Fresh traction is hard to compare honestly

`ratingCount` alone is not comparable across a 5-day-old listing and a 5-year-old listing.

The tool needs explicit age-normalized descriptive features and, when repeated observations actually exist, observed metric deltas.

The release must not fabricate short-window velocity when only one point exists.

## 1.3 Fresh anomaly discovery is useful but currently ad hoc

The Fresh Microhit Anomaly Sweep found useful unknown-unknowns, including the Satisfying Destruction challenger. That workflow should become reproducible.

The system should emit an **anomaly review queue**, not a hidden success score.

## 1.4 Semantic directness still requires human confirmation

M1.7 intentionally emits `direct_candidate`, not `confirmed_direct`.

There is no durable analyst-owned artifact for recording the manual verdict on the small candidate tail. 0.3 needs one so false positives, confirmed competitors, and unresolved cases can be preserved and reused.

## 1.5 Several theses are difficult to compare side by side

After running multiple focused sweeps, the analyst needs one comparable evidence table that answers questions such as:

```text
How much of the raw search union was noise?
How many direct candidates survived semantic triage?
How many were manually confirmed?
Are close competitors fresh or old?
What traction proxies are visible?
Did any fresh anomaly surface?
How complete is the evidence?
```

Reaper should provide those facts without producing BUILD / WATCH / SKIP automatically.

---

# 2. Release outcome

A successful 0.3 workflow should look conceptually like:

```text
versioned thesis suite
-> deterministic compile to existing analyst-experiment semantics
-> existing 0.2 collection / resume / verification
-> frozen market artifacts
-> M1.7 semantic/directness triage per thesis
-> age-normalized traction features
-> optional observed historical rating deltas when evidence exists
-> transparent fresh-anomaly queue
-> optional analyst directness review overlay
-> competitor-set quality summary
-> cross-thesis comparison artifact
-> compact JSON / CSV / Markdown evidence package
```

The output is decision support. It does not make the portfolio decision.

---

# 3. Scope

0.3 contains five product capabilities.

## 3.1 Thesis Suite v1

Introduce a versioned analyst input that groups several focused theses under one reproducible research suite.

Conceptual schema:

```json
{
  "spec_version": "thesis-suite-v1",
  "suite_id": "next-microgame-candidates-2026-09",
  "context": {
    "pages": 3,
    "session_profile": "clean_anonymous",
    "lang": "ru",
    "device": "desktop",
    "platform": "desktop_other"
  },
  "anomaly_policy": {
    "max_age_days": 180,
    "min_rating_count": 100,
    "min_lifetime_ratings_per_day": 5.0,
    "min_age_bucket_percentile": null
  },
  "theses": [
    {
      "thesis_id": "satisfying-destruction",
      "label": "destruction x ordinary objects",
      "queries": ["сломать предметы", "разбить всё", "destroy objects"],
      "semantic": {
        "theme_terms": ["предмет", "object"],
        "mechanic_terms": ["слом", "разб", "destroy", "break"],
        "reward_grammar_terms": ["разруш", "damage", "destroyed"]
      }
    }
  ]
}
```

Exact field names are implementation-owned, but the semantic contract is not:

- thesis IDs are explicit, versioned analyst input;
- exact queries and order remain analyst-owned;
- one thesis maps deterministically to one existing query family/comparable-set identity;
- semantic rules remain explicit and versioned;
- anomaly thresholds are explicit input, never hidden policy;
- context remains the same evidence-bearing context used by the existing experiment runner;
- the suite must compile deterministically to existing `analyst-experiment` inputs rather than introducing a second search/recovery implementation.

### Compatibility rule

The existing `analyst-experiment-v1.2` runner remains authoritative for:

```text
exact query collection
pagination
workdir ownership
resume
workers
raw persistence
comparable construction
rich metadata
snapshot/export/features
verification
artifact publication
```

0.3 MUST NOT clone these responsibilities into a new runner.

A thesis-suite convenience coordinator may call the existing runner and post-processing stages, but collection failure/resume remains governed by the existing experiment workdir and recovery contract.

## 3.2 Age-normalized traction and observed deltas

For every listing with the required evidence, 0.3 adds transparent descriptive traction features.

### Current-snapshot features

Required fields:

```text
snapshot_reference_time
first_published_at
listing_age_days
age_bucket
rating_count
lifetime_ratings_per_day
lifetime_pace_status
suite_age_bucket_cohort_size
suite_age_bucket_percentile
```

Recommended age buckets for v1:

```text
< 7 days
7–30 days
31–90 days
91–180 days
181–365 days
> 365 days
```

The exact boundary convention must be frozen in the implementation spec and tests.

### Lifetime pace rule

`lifetime_ratings_per_day` is a rough relative proxy only.

It must never be renamed or described as:

```text
DAU
plays/day
revenue/day
current growth rate
retention
```

For extremely young listings, denominator handling must remain explicit. v1 should prefer `unknown / too_young` over silently flooring age in a way that manufactures precision.

### Cohort percentile rule

An age-bucket percentile is relative only to the frozen comparison cohort used by the report.

The report must store:

```text
cohort definition
cohort size
observed/missing coverage
```

It must not be described as a Yandex-wide percentile unless the cohort actually represents a Yandex-wide frozen surface.

### Longitudinal delta rule

The production data model already supports repeated `game_metric_observations`. When at least two trustworthy observations of `rating_count` exist for the same listing, the 0.3 analyst layer may expose:

```text
previous_observed_at
previous_rating_count
current_observed_at
current_rating_count
delta_interval_days
rating_count_delta
observed_rating_delta_per_day
longitudinal_status
```

Important constraints:

- no prior observation -> `no_prior_observation`, not zero velocity;
- intervals that are too short for the declared v1 method remain flagged and cannot silently satisfy an anomaly gate;
- negative deltas are preserved as observed revisions/resets and are not clamped to zero;
- every delta binds the exact observation identities/provenance used;
- historical metric reads are bounded by the current report `as_of` time;
- no scheduler is added merely to create history.

0.3 benefits from history accumulated by normal research runs; it does not create a background monitoring service.

## 3.3 Fresh Anomaly Queue v1

The anomaly detector is a transparent filter over explicit analyst-owned thresholds.

Example policy:

```text
max_age_days <= 180
rating_count >= 100
lifetime_ratings_per_day >= 5
optional suite-relative age-bucket percentile >= configured value
optional observed delta velocity gate only when explicitly configured
```

The output is an ordered review queue with reason codes, for example:

```text
fresh_age_pass
rating_count_pass
lifetime_pace_pass
age_bucket_percentile_pass
observed_delta_unavailable
```

### Ordering

Ordering may use a declared deterministic sort such as:

```text
highest lifetime pace
then rating_count
then youngest age
then listing_id
```

This is queue ordering, not an opportunity score.

### Missing evidence

A configured gate whose required evidence is missing must be represented explicitly. The implementation must not silently convert missing data to zero or silently ignore the gate.

## 3.4 Directness Review + Competitor Quality v1

### Manual directness review artifact

Introduce a small analyst-owned, create-only review artifact that binds an exact semantic enrichment report hash.

Conceptual row:

```text
platform_listing_id
semantic_directness
a nalyst_verdict
reason_code
note
reviewed_at
```

Controlled v1 verdicts:

```text
confirmed_direct
adjacent
not_direct
unresolved
```

The artifact exists to preserve human confirmation, not to override raw evidence.

A review must fail closed if it references a listing outside the bound semantic report or if the bound report hash changes.

### Competitor-set quality summary

Per thesis, emit at minimum:

```text
raw_search_union_member_count
semantic_source_coverage
semantic_direct_candidate_count
semantic_adjacent_candidate_count
semantic_noise_candidate_count
semantic_insufficient_evidence_count
semantic_direct_candidate_share
reviewed_direct_candidate_count
confirmed_direct_count
rejected_direct_false_positive_count
unresolved_direct_candidate_count
manual_review_coverage
```

Also include query-surface quality where reproducible from frozen comparable evidence:

```text
query_count
per-query organic member counts
per-query unique contribution
pairwise overlap / Jaccard summary
members_seen_by_multiple_queries
```

The report must keep these as search-surface quality descriptors, not market-size estimates.

### Bounded whitespace statement

The machine-readable output may expose a controlled state such as:

```text
all_direct_candidates_reviewed_zero_confirmed
```

It must not emit an absolute statement such as `no competitors exist`.

The correct human interpretation remains:

> No meaningful direct match was confirmed inside the frozen researched surface under the declared rules.

## 3.5 Cross-Thesis Comparison v1

Produce one deterministic suite-level comparison over all declared theses.

Required per-thesis columns should include:

```text
thesis_id
raw_union_members
semantic_coverage
direct_candidates
adjacent_candidates
confirmed_direct
unresolved_direct_review
fresh_confirmed_direct
recent_release_share
best_confirmed_direct_rating_count
best_confirmed_direct_lifetime_pace
best_adjacent_rating_count
anomaly_candidate_count
longitudinal_velocity_coverage
query_surface_coherence
```

If a fact is unavailable, preserve `unknown` / `not_reviewed` / `not_applicable`; never substitute a nearby metric.

### No automatic winner

0.3 does not produce:

```text
opportunity_score
market_score
profitability_score
BUILD / WATCH / SKIP
recommended winner
```

The comparison artifact is deliberately factual so the portfolio decision layer can combine it with external trends, visual quality, production burden, CMF, monetization, portfolio overlap, and counterevidence.

---

# 4. Artifact model

0.3 should keep collection evidence immutable and separate from the new intelligence layer.

Recommended topology:

```text
existing experiment artifact
  artifacts/exports/<experiment_id>/<run_id>.zip

new thesis-intelligence artifact
  artifacts/intelligence/<suite_id>/<run_id>.zip
```

The intelligence artifact should contain conceptually:

```text
input/
  thesis-suite.json
  compiled-experiment-manifest.json
  semantic-theses/*.json

bindings/
  experiment-artifact.json

semantic/
  <thesis-id>.json
  <thesis-id>.csv

reviews/
  <thesis-id>.json        # only when supplied

theses/
  <thesis-id>-report.json
  <thesis-id>-report.csv

comparison/
  thesis-comparison.json
  thesis-comparison.csv
  thesis-comparison.md

artifact-manifest.json
```

Every canonical JSON report is content-hashed. The final ZIP is create-only and binds the SHA-256 of the exact source experiment artifact.

Rebuilding from the same frozen experiment artifact, suite declaration, method versions, and review artifacts must reproduce the same canonical reports.

Analyst-readable Markdown/CSV is derived convenience output; canonical JSON remains authoritative.

---

# 5. CLI surface

Recommended command family:

```text
yandex-reaper-thesis
```

## 5.1 `run`

```bash
yandex-reaper-thesis run path/to/suite.json
```

Responsibilities:

1. validate thesis suite;
2. deterministically compile the existing analyst experiment manifest and semantic declarations;
3. execute the existing experiment runner rather than reimplementing it;
4. after verified experiment publication, build thesis-intelligence outputs;
5. verify and publish the separate intelligence artifact.

If collection fails, recovery remains the existing experiment runner's responsibility. The command should surface the standard workdir/resume instruction and must not invent a second resume state machine.

## 5.2 `build`

```bash
yandex-reaper-thesis build \
  path/to/suite.json \
  --experiment-artifact artifacts/exports/...zip \
  --reviews path/to/reviews/
```

`build` is the important reproducibility path:

- no network access;
- verifies the source experiment artifact;
- regenerates semantic/traction/quality/comparison outputs from frozen evidence;
- allows review artifacts to be added after the initial collection;
- publishes create-only intelligence output.

This lets an analyst collect once, inspect the candidate tail, write reviews, and rebuild the final comparison without recollecting Yandex data.

## 5.3 `verify`

```bash
yandex-reaper-thesis verify path/to/intelligence.zip
```

Verification must cover:

```text
suite hash
source experiment artifact hash
compiled manifest identity
semantic report hashes
review bindings
per-thesis report hashes
comparison hash
artifact manifest / member hashes
```

---

# 6. Implementation sequencing

The release should be implemented in the following order. Each phase must be independently reviewable and must not silently expand the next phase.

## 0.3-P0 — Contract freeze

Deliverables:

- this product/spec document accepted;
- exact thesis-suite schema frozen;
- exact age-bucket semantics frozen;
- anomaly gate semantics frozen;
- manual directness review schema frozen;
- per-thesis and comparison report schemas frozen;
- compatibility/non-goal list accepted.

Exit gate:

> A developer can implement the release without inventing market semantics inside code.

## 0.3-P1 — Thesis suite compiler + artifact bindings

Implement:

- `ThesisSuiteDeclaration`;
- deterministic mapping `thesis -> existing query family`;
- deterministic compile to current experiment manifest semantics;
- deterministic compile to M1.7 semantic thesis declarations;
- experiment artifact binding model;
- create-only intelligence work/output paths;
- canonical hashing/verification primitives needed by later phases.

Tests:

- declaration validation;
- duplicate thesis/query rejection;
- exact order preservation;
- deterministic compiled bytes/model;
- no behavioral change for existing experiment runner inputs;
- source experiment hash mismatch fails closed.

No traction/anomaly logic yet.

## 0.3-P2 — Traction Features v1

Implement per-listing current snapshot features:

- first-publication age;
- frozen age bucket;
- rating count coverage;
- lifetime pace with explicit too-young/missing states;
- suite-relative age-bucket cohort percentile with cohort size/coverage.

Then add narrow historical metric read support only if the existing storage API cannot already supply the required previous `rating_count` observation.

Preferred storage rule:

- add a read API over the existing `game_metric_observations` model;
- no schema migration solely for 0.3 unless a concrete missing index is measured to be necessary;
- do not duplicate rating history into a new table.

Implement observed delta fields with exact observation bindings and explicit missing/revision states.

Tests:

- same-day/too-young listing;
- missing first-published;
- missing rating count;
- valid prior observation;
- no prior observation;
- negative rating delta;
- future timestamp fails closed;
- percentile cohort with missing members;
- deterministic tie handling.

## 0.3-P3 — Fresh Anomaly Queue v1

Implement explicit-policy filtering over P2 features.

Tests must prove:

- no hidden thresholds;
- each configured gate produces traceable pass/fail/unknown reason;
- missing configured evidence cannot silently pass;
- deterministic ordering;
- a 2-day-old listing is not granted fake precision by denominator flooring;
- queue labels are anomaly candidates, not success claims.

Acceptance fixture should reproduce the existing research style that used approximately:

```text
age <= 180 days
ratingCount >= 100
rough lifetime pace >= 5/day
```

as **declared run policy**, not hard-coded product truth.

## 0.3-P4 — Directness Review + Competitor Quality

Implement:

- versioned analyst review model;
- create-only review serialization helper/CLI path;
- exact semantic-report hash binding;
- review coverage calculations;
- confirmed/rejected/unresolved direct-candidate accounting;
- query contribution/overlap summaries from frozen comparable evidence;
- controlled bounded-whitespace state.

Tests:

- review of non-member fails;
- review against wrong semantic hash fails;
- duplicate review row fails;
- partial review remains partial;
- zero confirmed after 100% review does not become absolute absence;
- query overlap remains descriptive and does not mutate comparable membership.

## 0.3-P5 — Cross-Thesis Comparison

Implement suite-level deterministic comparison.

Requirements:

- declaration-order stable rows;
- no automatic score;
- direct and adjacent evidence never silently substituted for each other;
- best-traction values include listing IDs and evidence status, not naked numbers;
- explicit evidence coverage / unresolved review counts;
- JSON + CSV + concise Markdown summary.

Tests:

- thesis with zero direct candidates;
- thesis with unreviewed direct candidates;
- thesis with confirmed direct competitor;
- thesis with missing publication dates;
- thesis with anomaly candidate but no direct competitor;
- deterministic rebuild.

## 0.3-P6 — CLI integration

Implement `yandex-reaper-thesis run/build/verify` as a thin coordinator over completed components.

Hard rule:

> Do not duplicate the 0.2 runner's workdir/recovery/concurrency logic.

`run` delegates collection; `build` is pure frozen-evidence post-processing; `verify` is network-free.

Operational tests:

- collection failure surfaces existing resume path;
- successful existing experiment can be built independently;
- post-processing failure does not corrupt or mutate source experiment artifact;
- rebuilding with a different review artifact creates a different intelligence hash while preserving the same experiment binding;
- create-only publication cannot overwrite prior output.

## 0.3-P7 — Real-data validation + release

The release is not complete on synthetic fixtures alone.

### Validation A — Existing V3 replay controls

Use the frozen V3 artifact where possible to validate several known thesis shapes without new source collection.

Required controls:

1. **Custom Headphones** — known high fuzzy-noise / zero confirmed direct control.
2. **Custom Digicam** — expected weak direct supply / adjacent customization evidence.
3. **Restore Retro Tech** — expected near-direct cleaning/repair evidence and more production ambiguity.

The exact V3 artifact binding must be recorded in the validation report.

### Validation B — New Satisfying Destruction thesis sweep

Run one focused real collection for the current research challenger.

Questions to answer:

- how many meaningful direct destruction competitors exist in the researched surface?
- are any direct/adjacent examples fresh?
- does the existing anomaly still stand out after age normalization?
- are there multiple low-production examples or only one exceptional listing?
- does the new 0.3 workflow materially reduce manual analysis time?

This validation is both release acceptance and useful portfolio research.

### Release gate

Before `0.3.0` is tagged/bumped complete:

- all 0.3 specs match implementation;
- `ruff` passes;
- strict `mypy` passes;
- full `pytest` + repository coverage gate passes;
- existing 0.2 experiment acceptance behavior remains intact;
- V3 replay validation passes;
- Satisfying Destruction real validation produces a complete intelligence artifact;
- generated comparison is manually inspected for measurement honesty;
- relevant methodology/decision docs are synchronized when the real validation changes a durable conclusion;
- package version is bumped consistently to `0.3.0` only at final release completion.

---

# 7. Definition of Done

Reaper 0.3.0 is complete when an analyst can take several explicit theses and obtain one reproducible evidence package with substantially less manual CSV work.

Functional DoD:

- [ ] versioned `thesis-suite-v1` declaration exists;
- [ ] suite deterministically compiles to existing experiment semantics;
- [ ] M1.7 semantic enrichment runs per thesis automatically in the intelligence pipeline;
- [ ] per-listing age-normalized traction features exist with explicit coverage;
- [ ] historical rating delta is exposed only where two trustworthy observations exist;
- [ ] fresh anomaly queue uses explicit declared gates and reason codes;
- [ ] analyst directness reviews are durable, create-only, and hash-bound;
- [ ] per-thesis competitor-set quality summary exists;
- [ ] cross-thesis JSON/CSV/Markdown comparison exists;
- [ ] `run`, `build`, and `verify` workflow is available;
- [ ] intelligence artifacts bind and verify the immutable source experiment artifact;
- [ ] V3 replay controls pass;
- [ ] dedicated Satisfying Destruction live validation passes;
- [ ] full repository quality gate passes;
- [ ] package version/provenance is `0.3.0`.

Product DoD:

> For the validation suite, the analyst should spend time inspecting a compact evidence tail and making product judgements, not manually joining hundreds of fuzzy search rows across raw CSV files.

---

# 8. Explicit non-goals for 0.3

Do not add the following to this release:

```text
LLM classification inside Reaper
embeddings / vector DB
opaque opportunity score
automatic BUILD / WATCH / SKIP
automatic production-burden estimation
visual screenshot classifier
query-generation / synonym-expansion engine
Pinterest / TikTok / Google Trends ingestion
Steam / Google Play / App Store expansion
scheduler / daemon / monitoring service
dashboard / web UI
distributed workers
new generic workflow framework
broad taxonomy redesign
market-size estimator
Yandex-wide percentile claims from a narrow suite
fabricated 7d/30d/90d velocity without repeated observations
```

These may be reconsidered only after 0.3 real usage demonstrates a repeated decision bottleneck they would solve.

---

# 9. Deferred 0.3.1 / later candidates

Only after 0.3 validation, consider:

## Controlled query expansion

Object/action/result/reward axes with hard query budgets and provenance. Do not implement uncontrolled combinatorial expansion.

## Cross-thesis listing reuse report

Show listings repeatedly returned across multiple theses and where their semantic classifications differ. This may help diagnose generic Yandex search pollution.

## Sweep-to-sweep change detection

For repeated thesis research, summarize:

```text
new listings
new direct candidates
rating-count changes
removed/unobserved listings
review-status changes
```

This requires careful observation semantics and should not be pulled into 0.3 merely because it is adjacent.

## External trend binding

Potentially bind external trend evidence to a thesis report once a repeatable source/provenance contract is justified. External trend ingestion is not required for the 0.3 market-evidence workflow.

---

# 10. Scope guard

0.3 is successful if it makes the existing research loop cheaper and more reproducible.

It is a failure if implementation drifts toward:

```text
"one platform intelligence system"
"automatic game idea generator"
"AI market analyst"
"full analytics dashboard"
"generic orchestration platform"
```

The release boundary remains:

> collect trustworthy Yandex evidence, reduce fuzzy noise, expose fresh/relative traction transparently, preserve human directness judgement, and make several focused theses easy to compare.
