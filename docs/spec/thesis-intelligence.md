# Reaper 0.3.0 — Thesis Intelligence

## Status

**Release target:** `0.3.0`  
**Codename:** Thesis Intelligence  
**Scope status:** approved for planning; implementation status is owned by `/ROADMAP.md`.

This specification owns the analytical/product semantics for Reaper 0.3 Thesis Intelligence. It does not own implementation sequencing or Definition of Done; those remain exclusively in `/ROADMAP.md`.

The release exists to reduce the manual work between a focused Yandex Games thesis sweep and an evidence-backed project decision without turning Reaper into an automatic decision engine.

It is intentionally layered on the already-proven Reaper `0.2.0` experiment runner and the shipped M1.7 semantic/directness triage. It does not redefine collection, resume, worker, pagination, or immutable-evidence semantics.

---

# 1. Analytical problem

Real research exposed five repeated costs.

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

The current experiment runner collects query families and freezes comparable evidence. M1.7 can then reduce fuzzy search noise, but the analyst still has to connect these stages manually.

0.3 makes a focused thesis a first-class analyst workflow while preserving the existing collection boundary.

## 1.2 Fresh traction is hard to compare honestly

`ratingCount` alone is not comparable across a 5-day-old listing and a 5-year-old listing.

The analyst needs explicit age-normalized descriptive features and, only where repeated observations actually exist in explicitly frozen evidence, observed metric deltas.

The system must not fabricate short-window velocity from one point or read ambient mutable machine state during a deterministic rebuild.

## 1.3 Fresh anomaly discovery is useful but ad hoc

The Fresh Microhit Anomaly Sweep surfaced useful unknown-unknowns such as the Satisfying Destruction challenger.

That research mode should become reproducible as an **anomaly review queue**, not an opaque success score.

## 1.4 Semantic directness still requires human confirmation

M1.7 intentionally emits `direct_candidate`, not `confirmed_direct`.

0.3 therefore needs a durable analyst-owned review artifact so confirmed competitors, false positives, adjacent cases, and unresolved cases can be preserved against the exact frozen semantic report.

## 1.5 Cross-thesis comparison is too manual

After several focused sweeps the analyst needs one compact evidence surface answering questions such as:

```text
How much of the raw search union was noise?
How many direct candidates survived semantic triage?
How many were manually confirmed?
Are close competitors fresh or old?
What traction proxies are visible?
Did any fresh anomaly surface?
How complete is the evidence?
```

The output remains factual decision support. Reaper does not choose the project.

---

# 2. Release-level data flow

The intended analytical flow is:

```text
versioned thesis suite
-> deterministic compile to existing analyst-experiment semantics
-> existing 0.2 collection / resume / verification
-> frozen current experiment artifact
+ optional explicitly bound prior experiment artifacts
-> M1.7 semantic/directness triage per thesis
-> age-normalized traction features
-> optional observed historical rating deltas from bound prior artifacts
-> transparent fresh-anomaly queue
-> optional analyst directness review overlay
-> competitor-set quality summary
-> cross-thesis comparison artifact
-> compact JSON / CSV / Markdown evidence package
```

The new intelligence layer must remain reconstructable from immutable source artifacts and explicit analyst inputs.

---

# 3. Thesis Suite v1

Introduce a versioned analyst declaration that groups several focused theses under one reproducible suite.

Conceptual shape:

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

The exact Pydantic field layout is frozen during the roadmap contract phase, but the semantic rules are already fixed:

- thesis IDs are explicit versioned analyst input;
- exact queries and exact query order are analyst-owned evidence input;
- one thesis maps deterministically to one existing query-family/comparable-set identity in v1;
- semantic vocabulary remains explicit and versioned, not hidden in implementation code;
- anomaly thresholds are explicit input, not product-wide truth;
- context preserves the same evidence-bearing semantics used by the existing experiment runner;
- the suite compiles onto existing experiment semantics rather than introducing a second search/recovery implementation.

Historical artifact selection is an execution/build input rather than hidden global state. The exact prior artifact hashes used are frozen into the intelligence artifact bindings.

## 3.1 Compatibility boundary

The existing `analyst-experiment-v1.2` runner remains authoritative for:

```text
exact-query collection
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

0.3 must not clone these responsibilities.

A thesis coordinator may call the existing runner and later post-processing stages, but collection recovery remains governed by the existing experiment workdir contract.

Existing v1/v1.2 experiment manifests remain valid. A 0.3 thesis suite is an additive analyst layer, not a migration requirement for old experiments.

---

# 4. Age-normalized traction v1

For every listing with sufficient frozen evidence, the per-thesis report exposes transparent descriptive traction features.

## 4.1 Current-snapshot fields

Required semantic fields:

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

Recommended v1 age buckets are:

```text
< 7 days
7–30 days
31–90 days
91–180 days
181–365 days
> 365 days
```

Exact inclusive/exclusive boundaries are method semantics and must be versioned/frozen before implementation.

## 4.2 Lifetime pace semantics

`lifetime_ratings_per_day` is a rough relative proxy derived from Yandex listing age and `ratingCount`.

It must never be renamed or described as:

```text
DAU
plays/day
revenue/day
current growth rate
retention
```

Extremely young listings must not receive fabricated precision through an invisible denominator floor. The method must expose an explicit `too_young`/unavailable state when the v1 denominator prerequisite is not met.

Missing first-publication or rating-count evidence remains missing.

## 4.3 Suite-relative percentile semantics

An age-bucket percentile is relative only to the frozen cohort explicitly used by the report.

Every percentile must carry enough context to reconstruct:

```text
cohort definition
cohort size
observed count
missing count / coverage
```

A narrow suite-relative percentile must never be presented as Yandex-wide.

Ties must use a deterministic documented method.

---

# 5. Observed historical rating deltas v1

The current experiment artifact is authoritative for the current observation. Historical deltas may use only **explicitly bound immutable prior experiment artifacts**.

0.3 must not read a developer's ambient/current local SQLite database during `build` and call that deterministic history. Real V3 artifact inspection showed that a single experiment artifact can contain only one `rating_count` point per listing, so prior evidence must be supplied explicitly when longitudinal analysis is desired.

## 5.1 Historical artifact binding

`run`/`build` may accept zero or more prior experiment artifacts.

For every bound artifact, freeze at least:

```text
artifact path/reference
artifact_sha256
experiment_id
run_id
snapshot/reference time
verification status
```

The final intelligence artifact stores the exact ordered history-artifact bindings.

If no prior artifacts are supplied, longitudinal coverage is zero/unknown by evidence, not an error.

## 5.2 Prior observation selection

For one current listing, gather trustworthy prior `rating_count` observations from the explicitly bound prior artifacts only.

Selection rules:

- prior observation time must be strictly earlier than the current observation/reference time;
- future/equal-time observations are ineligible;
- if several valid prior observations exist, choose the latest deterministically by declared observation ordering;
- exact prior observation ID and source artifact hash are retained in the derived result;
- the same prior artifacts + current artifact must reproduce the same selected point.

## 5.3 Delta fields

When a trustworthy prior point exists, the analyst layer may expose:

```text
prior_artifact_sha256
previous_observation_id
previous_observed_at
previous_rating_count
current_observation_id
current_observed_at
current_rating_count
delta_interval_days
rating_count_delta
observed_rating_delta_per_day
longitudinal_status
```

Semantics:

- no eligible prior observation -> `no_prior_observation`, never zero velocity;
- interval below the frozen minimum method interval -> `interval_too_short` and cannot silently satisfy an anomaly velocity gate;
- negative deltas remain negative observed revisions/resets and are not clamped;
- both observations and their provenance are bound into the result;
- `build` may not query the network to fill missing history;
- no scheduler is introduced merely to generate history.

The term `observed_rating_delta_per_day` is intentionally distinct from `lifetime_ratings_per_day`.

Neither metric is a direct player-traffic measurement.

---

# 6. Fresh Anomaly Queue v1

The anomaly queue is a transparent filter over explicit suite policy.

Example declared policy:

```text
max_age_days <= 180
rating_count >= 100
lifetime_ratings_per_day >= 5
optional suite-relative age-bucket percentile >= configured value
optional observed rating-delta velocity gate when explicitly configured
```

No threshold above is universal product truth. The actual policy is stored in the suite declaration and bound into the report hash.

A longitudinal gate may only be configured/used against the explicitly bound historical-artifact evidence. Missing prior evidence remains visible.

## 6.1 Gate results

Each listing considered by the anomaly filter exposes traceable gate results/reasons, for example:

```text
fresh_age_pass
rating_count_pass
lifetime_pace_pass
age_bucket_percentile_not_configured
observed_delta_unavailable
```

A configured gate whose evidence is missing must not silently pass and must not silently disappear.

## 6.2 Queue ordering

A deterministic declared ordering may use descriptive values such as:

```text
lifetime pace descending
rating_count descending
age ascending
listing_id ascending
```

Ordering is review convenience, not a score or predicted success probability.

The output label is `anomaly_candidate` or equivalent. It must not call the listing a proven microhit, winner, or profitable game.

---

# 7. Analyst Directness Review v1

Introduce a small analyst-owned create-only artifact that binds an exact M1.7 semantic-enrichment content hash.

Conceptual row:

```text
platform_listing_id
semantic_directness
analyst_verdict
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

The exact reason-code vocabulary may be intentionally small; free-form notes cannot substitute for the controlled verdict.

Rules:

- every reviewed listing must exist in the bound semantic report;
- the semantic report content hash is mandatory;
- a review against a different report revision fails closed;
- duplicate/conflicting review rows for the same listing are invalid;
- partial review is valid and remains explicitly partial;
- the review records analyst judgement; it does not rewrite semantic evidence or raw source data;
- `reviewed_at` belongs to the review input itself and is not regenerated during deterministic rebuild.

---

# 8. Competitor-set quality v1

Per thesis, summarize how much useful competitor evidence survived each stage.

Required semantic fields:

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

## 8.1 Search-surface quality

Where reconstructable from frozen comparable evidence, also expose:

```text
query_count
per-query organic member count
per-query unique contribution
members seen by multiple queries
pairwise Jaccard / overlap summary
```

These values describe the **quality/coherence of the researched search surface**. They are not market-size or saturation estimates.

## 8.2 Bounded zero-direct state

If every semantic direct candidate has been reviewed and zero are confirmed, the machine-readable report may expose a controlled state such as:

```text
all_direct_candidates_reviewed_zero_confirmed
```

This means only:

> No meaningful direct match was confirmed inside the frozen researched surface under the declared queries and review rules.

It must never be rendered as `no competitors exist` or mathematical absence from Yandex Games.

---

# 9. Per-Thesis Intelligence Report v1

Each thesis receives one canonical report that references rather than silently rewrites its input artifacts.

Conceptual sections:

```text
identity
suite binding
current experiment/comparable binding
historical experiment artifact bindings
semantic report binding
optional review binding
traction rows
anomaly candidates
competitor-set quality
coverage / uncertainty
content_hash
```

The report must preserve listing IDs and evidence references for any highlighted best/maximum/minimum observation so numbers are never detached from their source listings.

Semantic directness, analyst verdict, freshness, and traction are separate dimensions. One must not be inferred from another.

---

# 10. Cross-Thesis Comparison v1

Produce one deterministic suite-level comparison in thesis declaration order.

Required per-thesis facts should include:

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

Exact field naming and recent-window semantics are frozen before implementation.

Rules:

- unavailable facts remain `unknown`, `not_reviewed`, or `not_applicable` as appropriate;
- direct evidence is never silently replaced with adjacent evidence;
- best-traction facts include the source listing identity and evidence status;
- unresolved review coverage stays visible;
- longitudinal coverage reflects only explicitly bound prior artifacts;
- comparison rows are stable by declaration order, not sorted into an implied winner ranking.

## 10.1 No automatic decision

0.3 does not produce:

```text
opportunity_score
market_score
profitability_score
BUILD / WATCH / SKIP
recommended winner
```

The portfolio decision layer must still combine Reaper evidence with factors Reaper does not know, including:

```text
external trend evidence
visual/thumbnail quality
production burden
Content Multiplication Factor
monetization fit
portfolio overlap
counterevidence
```

---

# 11. Artifact model

Collection evidence stays immutable and separate from the new intelligence artifact.

Recommended topology:

```text
current experiment artifact
  artifacts/exports/<experiment_id>/<run_id>.zip

optional prior experiment artifacts
  artifacts/exports/<prior-experiment-id>/<prior-run-id>.zip

thesis-intelligence artifact
  artifacts/intelligence/<suite_id>/<run_id>.zip
```

Conceptual intelligence contents:

```text
input/
  thesis-suite.json
  compiled-experiment-manifest.json
  semantic-theses/*.json

bindings/
  current-experiment-artifact.json
  history-experiment-artifacts.json

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

Canonical JSON is authoritative. CSV and Markdown are analyst-readable derived views.

Every canonical report is content-hashed. The final intelligence ZIP is create-only and binds the SHA-256 of the exact current experiment artifact and every prior experiment artifact actually used.

Rebuilding from the same current artifact, ordered prior artifacts, suite declaration, method versions, and review artifacts must reproduce the same canonical reports.

A different review artifact or historical artifact set legitimately produces a different intelligence report/artifact hash while preserving the current experiment binding.

---

# 12. CLI contract

Recommended command family:

```text
yandex-reaper-thesis
```

## 12.1 `run`

```bash
yandex-reaper-thesis run path/to/suite.json \
  [--history-artifact path/to/prior.zip ...]
```

Semantics:

1. validate the suite;
2. deterministically compile existing analyst experiment input plus semantic declarations;
3. delegate current collection to the established experiment runner;
4. verify any explicitly supplied prior experiment artifacts;
5. after verified current experiment publication, build thesis intelligence;
6. verify and publish the separate intelligence artifact.

If collection fails, the established experiment workdir/resume contract remains authoritative. `run` must not create a second thesis-specific recovery state machine.

## 12.2 `build`

```bash
yandex-reaper-thesis build \
  path/to/suite.json \
  --experiment-artifact artifacts/exports/...zip \
  [--history-artifact artifacts/exports/prior-1.zip ...] \
  [--reviews path/to/reviews/]
```

`build` is the canonical frozen-evidence reconstruction path:

- no network access;
- current and prior experiment artifacts are verified first;
- semantic/traction/quality/comparison reports are rebuilt only from bound frozen evidence;
- reviews may be added after collection without recollecting Yandex data;
- ambient local SQLite state is not consulted for historical deltas;
- outputs are create-only.

## 12.3 `verify`

```bash
yandex-reaper-thesis verify path/to/intelligence.zip
```

Verification covers at least:

```text
suite identity/hash
current experiment artifact hash
history experiment artifact hashes/order
compiled manifest identity
semantic report hashes
review bindings
per-thesis report hashes
comparison hash
artifact manifest/member hashes
```

`verify` is network-free.

---

# 13. Explicit non-goals

0.3 does not add:

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
ambient mutable local-DB history during deterministic build
fabricated 7d/30d/90d velocity without repeated frozen observations
```

These are not hidden stretch goals. Pulling one into 0.3 requires an explicit scope change and evidence that it solves a repeated decision bottleneck.

---

# 14. Deferred candidates

The following remain plausible later improvements but are outside the 0.3 semantic contract.

## Controlled query expansion

Potential object/action/result/reward axes with hard query budgets and provenance. Uncontrolled combinatorial expansion remains prohibited.

## Cross-thesis listing reuse diagnostics

Potential report showing listings repeatedly returned across multiple theses and where their semantic classifications differ. This may help diagnose generic Yandex search pollution.

## Sweep-to-sweep change detection

Potential longitudinal summary of:

```text
new listings
new direct candidates
rating-count changes
removed/unobserved listings
review-status changes
```

0.3 historical artifact binding provides a trustworthy building block but does not automatically turn this broader change-detection feature into current scope.

## External trend binding

Potential future binding of external trend evidence to thesis reports once a repeatable source/provenance contract is justified. External trend ingestion is not required for 0.3.

---

# 15. Scope guard

0.3 succeeds if it makes the existing research loop cheaper and more reproducible.

It fails if it drifts toward:

```text
one universal platform-intelligence system
automatic game idea generator
AI market analyst
full analytics dashboard
generic orchestration platform
```

The release boundary is:

> Collect trustworthy Yandex evidence through the existing runner, reduce fuzzy noise, expose fresh/relative traction transparently, preserve human directness judgement, and make several focused theses easy to compare from explicitly frozen evidence.
