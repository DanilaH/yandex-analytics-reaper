# Reaper 0.3 Thesis Intelligence — Frozen v1 Contracts

**Contract status:** FROZEN for 0.3 implementation  
**Parent semantics:** [`thesis-intelligence.md`](thesis-intelligence.md)  
**Implementation sequencing:** `/ROADMAP.md`

This document freezes the exact v1 analytical contracts that 0.3 implementation must follow. Code may choose module/class names, but it must not change these semantics without a new contract version and an explicit roadmap/doc update.

The contracts are additive over the existing `analyst-experiment-v1.2`, `analyst-market-export-v1`, and `analyst-semantic-enrichment-v1` artifacts.

---

# 1. Shared identity and validation rules

All canonical 0.3 Pydantic-style models use:

```text
frozen = true
extra = forbid
```

Slug identifiers use the existing experiment-compatible form:

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

with maximum length `80` unless an existing bound contract is stricter.

SHA-256 values are exactly 64 lowercase hexadecimal characters.

All timestamps are timezone-aware and canonical JSON serialization uses UTC ISO-8601 values.

Canonical JSON hashing uses:

```text
UTF-8
ensure_ascii = false
sort_keys = true
separators = (",", ":")
SHA-256 over exact canonical bytes
```

Local filesystem paths are invocation inputs only. They are never semantic identity and MUST NOT be included in canonical artifact bindings or report hashes.

---

# 2. `thesis-suite-v1`

## 2.1 Suite model

Canonical shape:

```text
ThesisSuiteDeclaration
  spec_version: "thesis-suite-v1"
  suite_id: slug
  suite_version: int >= 1
  context: ThesisSuiteContext
  anomaly_policy: ThesisAnomalyPolicy | null
  theses: tuple[ThesisDeclaration, ...] length >= 1
```

`ThesisSuiteContext` is field-for-field compatible with the existing `AnalystExperimentContext`:

```text
pages: int >= 1
session_profile: "clean_anonymous"
lang: non-blank trimmed string
device: "desktop" | "mobile"
platform: non-blank trimmed string
```

No new evidence-bearing context dimensions are introduced in 0.3.

## 2.2 Thesis model

```text
ThesisDeclaration
  thesis_id: slug
  thesis_version: int >= 1
  label: non-blank trimmed string
  queries: tuple[non-blank trimmed string, ...] length >= 1
  semantic: ThesisSemanticDeclaration
```

Within one suite:

- `thesis_id` values are unique;
- every exact query string is unique across the entire suite, matching the existing experiment-manifest rule that one exact query may belong to only one family;
- query order is semantic analyst input and is preserved exactly;
- thesis declaration order is semantic analyst input and is preserved exactly.

`ThesisSemanticDeclaration`:

```text
theme_terms: tuple[string, ...] length >= 1
mechanic_terms: tuple[string, ...] length >= 1
reward_grammar_terms: tuple[string, ...] | null
```

Term validation is identical to `AnalystSemanticRule`: non-blank, already trimmed, and unique after the existing semantic normalization/case-folding behavior.

## 2.3 Deterministic compile contract

A suite compiles to exactly one existing `AnalystExperimentManifest`:

```text
schema_version = 1
experiment_id = suite_id
context = suite.context
families = suite.theses in declaration order
```

For thesis `T`:

```text
family.id      = T.thesis_id
family.queries = T.queries
```

Therefore the existing runner constructs:

```text
query_family_id = thesis_id
query_family_version = 1
comparable_set_id = <suite_id>--<thesis_id>
comparable_set_version = 1
```

No 0.3 code may invent a second query-family or comparable-set naming scheme.

Each thesis also compiles to one existing `AnalystSemanticThesisDeclaration`:

```text
spec_version = "analyst-semantic-thesis-v1"
thesis_id = T.thesis_id
version = T.thesis_version
label = T.label
target_set_ids = ("<suite_id>--<thesis_id>",)
theme.terms = T.semantic.theme_terms
mechanic.terms = T.semantic.mechanic_terms
reward_grammar = null OR rule(T.semantic.reward_grammar_terms)
```

The same suite bytes must always compile to semantically equal existing experiment/semantic declarations.

`suite_version` does not mutate the existing experiment manifest schema. It remains intelligence-layer provenance and allows a later suite revision to be distinguishable even if `suite_id` is retained.

---

# 3. `thesis-anomaly-policy-v1`

`anomaly_policy = null` disables anomaly qualification while leaving traction features available.

When configured:

```text
ThesisAnomalyPolicy
  spec_version: "thesis-anomaly-policy-v1"
  max_age_days: float > 0 | null
  min_rating_count: int >= 0 | null
  min_lifetime_ratings_per_day: float >= 0 | null
  min_age_bucket_percentile: float in [0, 1] | null
  min_observed_rating_delta_per_day: float >= 0 | null
```

At least one gate must be configured.

No values above are hard-coded market truth. They are explicit analyst input and are included in suite/report hashes.

Anomaly queue ordering is fixed in v1 and is not configurable:

```text
1. lifetime_ratings_per_day descending, unavailable last
2. rating_count descending, unavailable last
3. listing_age_days ascending, unavailable last
4. platform_listing_id ascending
```

---

# 4. Experiment artifact bindings

## 4.1 Current binding

Canonical current binding:

```text
ExperimentArtifactBinding
  spec_version: "thesis-experiment-binding-v1"
  role: "current"
  artifact_sha256
  artifact_manifest_sha256
  experiment_id
  run_id
  manifest_sha256
  snapshot_id
  snapshot_content_hash
  snapshot_created_at
  market_export_content_hash
  market_features_content_hash
  verifier_status: "pass"
```

All values are verified from the immutable source ZIP before use. The invocation-local path is not stored in this binding.

The current artifact MUST:

- pass existing packaged-artifact verification;
- bind the compiled experiment `experiment_id == suite_id`;
- contain the compiled manifest bytes expected from the suite;
- bind the exact snapshot/export/features hashes later used by intelligence derivation.

## 4.2 Prior/history binding

Canonical prior binding uses the same model except:

```text
role: "prior"
```

Zero or more prior artifacts may be supplied.

The canonical prior binding tuple is sorted by:

```text
snapshot_created_at ascending
then experiment_id ascending
then run_id ascending
then artifact_sha256 ascending
```

CLI declaration order is not semantic history order.

Duplicate `artifact_sha256` values are rejected.

A prior artifact MAY come from another experiment/suite. Longitudinal matching happens by `platform_listing_id`, not by experiment identity.

The current artifact hash must not also appear in the prior tuple.

---

# 5. `traction-features-v1`

## 5.1 Reference time and age

Current listing age is computed from:

```text
reference_time = current AnalystSnapshotReport.created_at
first_published_at = current AnalystMarketExportReport.listings[*].first_published_at
listing_age_days = exact elapsed seconds / 86_400
```

`listing_age_days` is a finite non-negative float. A source publication timestamp after `reference_time` fails closed.

Missing `first_published_at` produces missing age/bucket; it is never converted to zero.

## 5.2 Frozen age buckets

`AgeBucketV1`:

```text
lt_7_days      : 0 <= age < 7
7_30_days      : 7 <= age < 31
31_90_days     : 31 <= age < 91
91_180_days    : 91 <= age < 181
181_365_days   : 181 <= age < 366
over_365_days  : age >= 366
```

The labels describe elapsed whole-day ranges while the actual age value remains a float.

## 5.3 Current rating evidence

`rating_count` comes only from the current `AnalystListingRow.rating_count` resolved value.

For observed rating count, retain:

```text
rating_count: int >= 0
rating_count_observation_id
rating_count_observed_at
```

The numeric value must be integral. A non-integral numeric `rating_count` fails closed rather than being rounded.

Missing current rating count remains missing with no observation ID/timestamp.

## 5.4 Lifetime pace

`LifetimePaceStatusV1`:

```text
observed
missing_first_published
missing_rating_count
too_young
```

Method prerequisite:

```text
listing_age_days >= 1.0
```

If the prerequisite is met and rating count is observed:

```text
lifetime_ratings_per_day = rating_count / listing_age_days
status = observed
```

If `0 <= age < 1.0`:

```text
lifetime_ratings_per_day = null
status = too_young
```

No denominator flooring is permitted.

## 5.5 Suite-relative age-bucket cohort percentile

The percentile cohort is defined across **unique platform listing IDs in the current suite artifact**, not separately per thesis.

A listing participates in its bucket cohort only when:

```text
age_bucket is observed
AND lifetime_pace_status == observed
```

Because one suite compiles to one experiment artifact, a listing returned by several thesis comparables is deduplicated by `platform_listing_id` before cohort construction.

For one listing with lifetime pace `x` in a cohort of size `n`:

```text
suite_age_bucket_percentile = count(cohort pace <= x) / n
```

This empirical-CDF rule gives equal values the same percentile. For a singleton cohort the percentile is `1.0`; the report must still expose `cohort_size = 1` so the analyst can see the weak denominator.

Per traction row expose:

```text
suite_age_bucket_cohort_size
suite_age_bucket_observed_count
suite_age_bucket_percentile
```

Rows without an eligible cohort value expose percentile `null` and size/count `0` or the relevant bucket cohort size as defined by the implementation model; they must not fabricate rank.

---

# 6. `longitudinal-rating-delta-v1`

## 6.1 Current observation

The current point is the current market-export `rating_count` evidence:

```text
current_observation_id
current_observed_at
current_rating_count
```

If current rating count is missing, longitudinal status is `current_missing` and no prior selection is attempted.

## 6.2 Eligible prior points

For the same `platform_listing_id`, inspect only verified explicitly bound prior artifacts.

A prior point is eligible only when:

```text
prior rating_count is observed
prior observed_at < current_observed_at
```

Equal/future timestamps are ineligible.

Choose the eligible point with the greatest `observed_at`.

If more than one prior candidate shares that greatest timestamp:

- identical numeric values are equivalent; choose the lexicographically smallest `(artifact_sha256, observation_id)` for stable provenance;
- conflicting numeric values at the same timestamp are an evidence conflict and the build fails closed.

## 6.3 Delta method

`LongitudinalStatusV1`:

```text
observed
negative_revision
current_missing
no_prior_observation
interval_too_short
```

Minimum interval:

```text
1.0 day (86_400 seconds)
```

For an eligible point:

```text
delta_interval_days = exact elapsed seconds / 86_400
rating_count_delta = current_rating_count - previous_rating_count
```

If interval `< 1.0` day:

```text
observed_rating_delta_per_day = null
status = interval_too_short
```

Otherwise:

```text
observed_rating_delta_per_day = rating_count_delta / delta_interval_days
status = negative_revision if rating_count_delta < 0 else observed
```

Negative values are preserved. They are not clamped and are not interpreted as negative traffic.

Every non-missing selected-prior result binds:

```text
prior_artifact_sha256
previous_observation_id
previous_observed_at
previous_rating_count
```

---

# 7. Traction row contract

Canonical per-listing row:

```text
ThesisTractionRow
  platform_listing_id
  external_app_id
  canonical_url
  title: string | null

  first_published_at: timestamp | null
  first_published_observation_id: string | null
  listing_age_days: float | null
  age_bucket: AgeBucketV1 | null

  rating_count: int | null
  rating_count_observation_id: string | null
  rating_count_observed_at: timestamp | null

  lifetime_ratings_per_day: float | null
  lifetime_pace_status: LifetimePaceStatusV1

  suite_age_bucket_cohort_size: int >= 0
  suite_age_bucket_observed_count: int >= 0
  suite_age_bucket_percentile: float in [0,1] | null

  longitudinal: LongitudinalRatingDeltaV1
```

Rows follow the thesis comparable member order from the frozen snapshot.

The traction row does not contain semantic or analyst-review verdicts. Those remain separate dimensions in the report.

---

# 8. Anomaly evaluation contract

`AnomalyGateStatusV1`:

```text
pass
fail
unknown
not_configured
```

Every traction row receives one `AnomalyEvaluationV1` when `anomaly_policy` is configured:

```text
platform_listing_id
max_age_days_status
min_rating_count_status
min_lifetime_ratings_per_day_status
min_age_bucket_percentile_status
min_observed_rating_delta_per_day_status
is_anomaly_candidate: bool
```

Gate rules:

- unconfigured field -> `not_configured`;
- configured field + missing/unusable evidence -> `unknown`;
- configured field + usable value meeting threshold -> `pass`;
- configured field + usable value not meeting threshold -> `fail`.

Specific longitudinal behavior:

- `observed` with a numeric delta can pass/fail;
- `negative_revision` has a numeric delta and therefore normally fails any non-negative minimum;
- `current_missing`, `no_prior_observation`, `interval_too_short` -> `unknown`.

Qualification rule:

```text
is_anomaly_candidate = true
IFF every configured gate status == pass
```

`unknown` never silently qualifies.

When `anomaly_policy = null`, the report stores no anomaly evaluations and the queue is empty with explicit status `disabled`.

---

# 9. `analyst-directness-review-v1`

The v1 review artifact intentionally reviews the semantic **direct-candidate tail only**. If repeated false negatives are discovered in adjacent/noise rows, the correct action is to revise/version the thesis semantic rules rather than silently override them inside this artifact.

Canonical artifact:

```text
AnalystDirectnessReviewPayload
  spec_version: "analyst-directness-review-v1"
  suite_id
  suite_version
  thesis_id
  thesis_version
  semantic_report_content_hash
  review_scope: "direct_candidates"
  rows: tuple[AnalystDirectnessReviewRow, ...]

AnalystDirectnessReviewReport
  <payload fields>
  content_hash
```

`rows` may be empty, representing an explicit empty review artifact, although omission of a review artifact is preferable when no review has occurred.

Row:

```text
platform_listing_id
semantic_directness: "direct_candidate"
analyst_verdict: confirmed_direct | adjacent | not_direct | unresolved
reason_code: DirectnessReasonCodeV1
note: trimmed string | null
reviewed_at: aware timestamp
```

`DirectnessReasonCodeV1`:

```text
direct_mechanic_and_theme
theme_incidental
mechanic_mismatch
theme_mismatch
mechanic_applies_to_other_object
broader_multi_object_scope
insufficient_context
other
```

Rules:

- listing must exist in bound semantic report;
- bound semantic row must actually be `direct_candidate`;
- row `semantic_directness` must equal the semantic report value;
- listing IDs are unique inside the review artifact;
- `other` requires a non-empty note;
- `confirmed_direct` normally uses `direct_mechanic_and_theme`; inconsistent verdict/reason combinations are not universally forbidden because the controlled reason records the analyst's rationale, but `confirmed_direct + theme_incidental/theme_mismatch/mechanic_mismatch/mechanic_applies_to_other_object` is invalid;
- `reviewed_at` is analyst input and is never regenerated during rebuild.

Canonical review row order follows semantic-report listing order, not review-file input order.

---

# 10. Competitor quality contract

Canonical `CompetitorQualityV1` fields:

```text
raw_search_union_member_count

semantic_source_observed_count
semantic_source_missing_count
semantic_source_coverage_ratio

semantic_direct_candidate_count
semantic_adjacent_candidate_count
semantic_noise_candidate_count
semantic_insufficient_evidence_count
semantic_direct_candidate_share

review_artifact_present
reviewed_direct_candidate_count
confirmed_direct_count
adjacent_after_review_count
rejected_direct_false_positive_count
unresolved_direct_candidate_count
manual_direct_review_coverage_ratio

direct_review_state:
  not_reviewed
  partially_reviewed
  all_reviewed_with_confirmed
  all_direct_candidates_reviewed_zero_confirmed
  no_direct_candidates

query_surface: QuerySurfaceQualityV1
```

Definitions:

```text
semantic_source_observed_count = semantic rows with source != null
semantic_source_missing_count = raw union - observed
semantic_source_coverage_ratio = observed / raw union
semantic_direct_candidate_share = direct candidates / raw union
```

`rejected_direct_false_positive_count` counts review verdicts `adjacent` or `not_direct`.

Manual review coverage denominator is semantic direct-candidate count. If there are zero direct candidates, coverage ratio is `null` and `direct_review_state = no_direct_candidates`.

## 10.1 Query surface quality

`QuerySurfaceQualityV1`:

```text
query_count
members_seen_by_multiple_queries
multi_query_member_share
mean_pairwise_jaccard: float | null
median_pairwise_jaccard: float | null
queries: tuple[QueryContributionV1, ...]
pairwise: tuple[PairwiseQueryOverlapV1, ...]
```

`QueryContributionV1`:

```text
query_text
organic_member_count
unique_contribution_count
```

`unique_contribution_count` is the count of comparable members whose organic search evidence includes this query and no other thesis query.

`PairwiseQueryOverlapV1`:

```text
left_query
right_query
intersection_count
union_count
jaccard: float | null
```

Pairwise ordering follows query declaration order combinations `(0,1), (0,2), ...`.

`mean_pairwise_jaccard` and `median_pairwise_jaccard` use only non-null pairwise values. They are null when no numeric pairwise value exists.

These are search-surface coherence descriptors only.

---

# 11. Per-thesis intelligence report

Canonical payload:

```text
ThesisIntelligencePayload
  spec_version: "thesis-intelligence-report-v1"
  method_version: "thesis-intelligence-method-v1"

  suite_id
  suite_version
  thesis_id
  thesis_version
  label

  current_experiment: ExperimentArtifactBinding(role=current)
  prior_experiments: tuple[ExperimentArtifactBinding(role=prior), ...]

  comparable_set_id
  comparable_set_version
  semantic_report_content_hash
  review_content_hash: string | null

  traction: tuple[ThesisTractionRow, ...]
  anomaly_policy: ThesisAnomalyPolicy | null
  anomaly_status: enabled | disabled
  anomaly_evaluations: tuple[AnomalyEvaluationV1, ...]
  anomaly_candidate_listing_ids: tuple[string, ...]

  competitor_quality: CompetitorQualityV1

ThesisIntelligenceReport
  <payload fields>
  content_hash
```

Invariant rules:

- traction listing order exactly matches frozen comparable member order;
- anomaly candidate IDs exactly match evaluation rows with `is_anomaly_candidate=true`, sorted by the frozen queue ordering, not comparable order;
- review hash is null when no review artifact is supplied;
- prior artifact tuple is the canonical sorted binding tuple from section 4;
- report cannot reference a listing outside its comparable set;
- semantic report must bind the exact current snapshot and exact thesis target set;
- review artifact, when present, must bind this semantic report hash and thesis identity.

---

# 12. Cross-thesis comparison contract

Canonical report:

```text
ThesisComparisonPayload
  spec_version: "thesis-comparison-v1"
  suite_id
  suite_version
  current_experiment_artifact_sha256
  prior_experiment_artifact_sha256s
  thesis_report_hashes
  rows: tuple[ThesisComparisonRow, ...]

ThesisComparisonReport
  <payload fields>
  content_hash
```

Rows follow suite thesis declaration order exactly.

`ThesisComparisonRow`:

```text
thesis_id
thesis_version
label

raw_union_members
semantic_coverage_ratio
direct_candidates
adjacent_candidates
confirmed_direct
unresolved_direct_review

fresh_confirmed_direct_180d
recent_release_180d_share
recent_release_coverage_ratio

best_confirmed_direct_rating_count: ListingMetricHighlightV1 | null
best_confirmed_direct_lifetime_pace: ListingMetricHighlightV1 | null
best_adjacent_rating_count: ListingMetricHighlightV1 | null

anomaly_candidate_count
longitudinal_observed_count
longitudinal_coverage_ratio
mean_pairwise_query_jaccard
multi_query_member_share
```

Fresh/recent v1 window is frozen to:

```text
listing_age_days <= 180.0
```

`recent_release_180d_share` denominator is listings with observed first-publication age in that thesis comparable set. `recent_release_coverage_ratio` exposes the corresponding observed-age coverage.

Longitudinal observed coverage counts rows whose longitudinal status is `observed` or `negative_revision` and whose numeric delta rate therefore exists. `interval_too_short` is not counted as observed velocity coverage.

`ListingMetricHighlightV1`:

```text
platform_listing_id
title: string | null
metric_name: rating_count | lifetime_ratings_per_day
value: finite float
observation_id: string | null
status: observed
```

For ties choose the earliest listing in frozen comparable member order.

`best_adjacent_rating_count` uses semantic `adjacent_candidate` rows only. It is never substituted when direct evidence is unavailable.

No comparison field encodes winner/recommendation/order-of-preference.

---

# 13. Intelligence artifact identity

Canonical final ZIP location convention:

```text
artifacts/intelligence/<suite_id>/<run_id>.zip
```

`run_id` is the current bound experiment run ID. The artifact is create-only.

Canonical payload members:

```text
input/thesis-suite.json
input/compiled-experiment-manifest.json
input/semantic-theses/<thesis-id>.json

bindings/current-experiment-artifact.json
bindings/history-experiment-artifacts.json

semantic/<thesis-id>.json
semantic/<thesis-id>.csv

reviews/<thesis-id>.json              # only when supplied

theses/<thesis-id>-report.json
theses/<thesis-id>-report.csv

comparison/thesis-comparison.json
comparison/thesis-comparison.csv
comparison/thesis-comparison.md

artifact-manifest.json
```

The intelligence artifact manifest uses its own version:

```text
thesis-intelligence-artifact-v1
```

and stores sorted member path/size/SHA-256 entries, excluding itself from its member hash list, following the same create-only/verification principles as the experiment artifact.

A rebuild from the same canonical suite declaration, verified current/prior artifacts, method versions, and review artifacts must reproduce semantically equal canonical JSON reports and the same member bytes apart from ZIP container metadata. Verification is therefore member/hash based; the ZIP file's own binary SHA may differ if ZIP metadata serialization differs, unless implementation deliberately freezes ZIP metadata too.

---

# 14. Measurement-honesty invariants

The following are contract violations in 0.3:

```text
calling lifetime_ratings_per_day a current growth rate
calling rating delta plays/day or DAU
silently flooring listing age to create a pace
using mutable ambient SQLite state in deterministic build
using a prior artifact without freezing/verifying its hash
silently ignoring a configured anomaly gate when evidence is missing
counting semantic direct_candidate as confirmed competitor truth
turning zero confirmed direct candidates into absolute market absence
using adjacent evidence as a fallback for a missing direct metric
sorting comparison rows into an implied winner order
adding BUILD/WATCH/SKIP or opportunity score to these contracts
```

If implementation cannot satisfy a requested output without violating one of these invariants, the correct output is explicit missing/unknown evidence or a failed build, not an inferred substitute.
