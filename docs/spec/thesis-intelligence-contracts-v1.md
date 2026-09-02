# Reaper 0.3 Thesis Intelligence — Frozen v1 Contracts

**Contract status:** FROZEN for 0.3 implementation  
**Parent semantics:** [`thesis-intelligence.md`](thesis-intelligence.md)  
**Implementation sequencing:** `/ROADMAP.md`

This document freezes the exact v1 analytical contracts that 0.3 implementation must follow. Code may choose module/class names, but it must not change these semantics without a new contract version and an explicit roadmap/doc update.

The contracts are additive over the existing `analyst-experiment-v1.2`, `analyst-market-export-v1`, and `analyst-semantic-enrichment-v1` artifacts.

---

# 1. Shared identity and canonicalization

All canonical 0.3 Pydantic-style models use:

```text
frozen = true
extra = forbid
```

Slug identifiers use the existing experiment-compatible pattern:

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

with maximum length `80` unless an existing bound contract is stricter.

SHA-256 values are exactly 64 lowercase hexadecimal characters.

All semantic timestamps are timezone-aware and normalized to UTC before canonical hashing. Canonical timestamp text uses ISO-8601 with `Z`.

Canonical JSON hashing uses:

```text
UTF-8
ensure_ascii = false
sort_keys = true
separators = (",", ":")
SHA-256 over exact canonical bytes
```

Invocation-local filesystem paths are operational inputs only. They are never semantic identity and MUST NOT appear in canonical artifact bindings or report hashes.

---

# 2. `thesis-suite-v1`

## 2.1 Suite declaration

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

No new evidence-bearing context dimension is introduced by 0.3.

## 2.2 Thesis declaration

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
- every exact query string is unique across the entire suite, matching the existing experiment rule that one exact query belongs to only one family;
- thesis declaration order is preserved exactly;
- query declaration order is preserved exactly.

`ThesisSemanticDeclaration`:

```text
theme_terms: tuple[string, ...] length >= 1
mechanic_terms: tuple[string, ...] length >= 1
reward_grammar_terms: tuple[string, ...] | null
```

Term validation is identical to `AnalystSemanticRule`: each term is non-blank, already trimmed, searchable after existing semantic normalization, and unique after normalization/case-folding.

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

Therefore the existing runner remains authoritative for the resulting identities:

```text
query_family_id = thesis_id
query_family_version = 1
comparable_set_id = <suite_id>--<thesis_id>
comparable_set_version = 1
```

No 0.3 code may invent a second query-family/comparable naming scheme.

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

The same suite declaration must always compile to semantically equal experiment and semantic declarations.

`suite_version` remains intelligence-layer provenance; it does not alter the existing experiment-manifest schema.

---

# 3. `thesis-anomaly-policy-v1`

`anomaly_policy = null` disables anomaly qualification while leaving traction features enabled.

Configured shape:

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

These values are analyst input, not global market truth, and are included in suite/report hashes.

V1 queue ordering is fixed:

```text
1. lifetime_ratings_per_day descending, unavailable last
2. rating_count descending, unavailable last
3. listing_age_days ascending, unavailable last
4. platform_listing_id ascending
```

---

# 4. Experiment artifact bindings

## 4.1 Canonical binding

```text
ExperimentArtifactBinding
  spec_version: "thesis-experiment-binding-v1"
  role: "current" | "prior"
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

Every value is reconstructed from and verified against the immutable source ZIP before use.

The invocation-local path is not persisted in this binding.

## 4.2 Current artifact requirements

The current artifact MUST:

- pass the existing packaged-experiment verification path;
- satisfy `experiment_id == suite_id`;
- contain input manifest bytes semantically equal to the suite's deterministic compiled experiment manifest;
- bind the exact snapshot/export/features artifacts consumed by intelligence derivation.

## 4.3 Prior artifact rules

Zero or more prior experiment artifacts may be supplied.

A prior artifact may come from another experiment/suite. Longitudinal matching uses `platform_listing_id`, not experiment identity.

Duplicate `artifact_sha256` values are invalid. The current artifact hash may not appear in the prior set.

Canonical prior binding order is:

```text
snapshot_created_at ascending
then experiment_id ascending
then run_id ascending
then artifact_sha256 ascending
```

CLI declaration order is operational only and cannot change a canonical rebuild.

---

# 5. `traction-features-v1`

## 5.1 Reference time and listing age

```text
reference_time = current AnalystSnapshotReport.created_at
first_published_at = current AnalystMarketExportReport.listings[*].first_published_at
listing_age_days = exact elapsed seconds / 86_400
```

`listing_age_days` is a finite non-negative float.

A publication timestamp after `reference_time` fails closed. Missing publication evidence remains missing and never becomes zero age.

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

The actual age value remains a float; bucket labels describe elapsed whole-day ranges.

## 5.3 Current rating-count evidence

`rating_count` comes only from the current `AnalystListingRow.rating_count` resolved value.

Observed fields:

```text
rating_count: int >= 0
rating_count_observation_id
rating_count_observed_at
```

The source numeric value must be integral. A non-integral numeric value fails closed rather than being rounded.

Missing rating count yields null value/observation/timestamp.

## 5.4 Lifetime pace

`LifetimePaceStatusV1`:

```text
observed
missing_first_published
missing_rating_count
too_young
```

Minimum denominator prerequisite:

```text
listing_age_days >= 1.0
```

When age and rating count are observed and age is at least one day:

```text
lifetime_ratings_per_day = rating_count / listing_age_days
status = observed
```

When `0 <= age < 1.0`:

```text
lifetime_ratings_per_day = null
status = too_young
```

No denominator flooring is allowed.

## 5.5 Suite-relative age-bucket percentile

The percentile cohort is constructed across **unique `platform_listing_id` values in the current suite artifact**, not separately per thesis.

For one age bucket define:

```text
bucket_member_count
= unique current-suite listings with that observed age_bucket

bucket_pace_observed_count
= bucket members with lifetime_pace_status == observed

bucket_pace_coverage_ratio
= bucket_pace_observed_count / bucket_member_count
```

A listing returned by several thesis comparables participates once in the suite cohort.

For a row whose pace is observed, with value `x`, calculate empirical-CDF percentile over the observed pace subset:

```text
suite_age_bucket_percentile
= count(observed bucket pace <= x) / bucket_pace_observed_count
```

Tied pace values therefore receive the same percentile. A singleton observed pace cohort receives percentile `1.0`; the explicit denominator remains visible.

Every traction row with an observed age bucket carries:

```text
suite_age_bucket_member_count >= 1
suite_age_bucket_pace_observed_count >= 0
suite_age_bucket_pace_coverage_ratio in [0,1]
```

If the row's age bucket is missing, all three fields are null.

If the age bucket exists but the row's own lifetime pace is unavailable, `suite_age_bucket_percentile = null` while the bucket member/coverage fields still describe the real cohort.

---

# 6. `longitudinal-rating-delta-v1`

## 6.1 Current point

The current point is the current market-export rating-count evidence:

```text
current_observation_id
current_observed_at
current_rating_count
```

If current rating count is missing, longitudinal status is `current_missing`; no prior point is selected.

## 6.2 Eligible prior points

For the same `platform_listing_id`, inspect only verified explicitly bound prior artifacts.

A prior point is eligible only when:

```text
prior rating_count is observed
prior observed_at < current_observed_at
```

Choose the eligible point with the greatest `observed_at`.

If several candidates share that greatest timestamp:

- if their numeric values are identical, choose lexicographically smallest `(artifact_sha256, observation_id)` for stable provenance;
- if their numeric values differ, the history is conflicting and the build fails closed.

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
1.0 day = 86_400 seconds
```

For one selected prior point:

```text
delta_interval_days = exact elapsed seconds / 86_400
rating_count_delta = current_rating_count - previous_rating_count
```

If interval `< 1.0`:

```text
observed_rating_delta_per_day = null
status = interval_too_short
```

Otherwise:

```text
observed_rating_delta_per_day = rating_count_delta / delta_interval_days
status = negative_revision if rating_count_delta < 0 else observed
```

Negative deltas are preserved; they are not interpreted as negative traffic.

A selected prior point always binds:

```text
prior_artifact_sha256
previous_observation_id
previous_observed_at
previous_rating_count
```

---

# 7. Traction row contract

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

  suite_age_bucket_member_count: int >= 1 | null
  suite_age_bucket_pace_observed_count: int >= 0 | null
  suite_age_bucket_pace_coverage_ratio: float in [0,1] | null
  suite_age_bucket_percentile: float in [0,1] | null

  longitudinal: LongitudinalRatingDeltaV1
```

Rows follow the frozen thesis comparable member order.

Traction rows do not contain semantic directness or analyst review verdicts; those remain separate report dimensions.

---

# 8. Anomaly evaluation

`AnomalyGateStatusV1`:

```text
pass
fail
unknown
not_configured
```

When policy is enabled every traction row receives:

```text
AnomalyEvaluationV1
  platform_listing_id
  max_age_days_status
  min_rating_count_status
  min_lifetime_ratings_per_day_status
  min_age_bucket_percentile_status
  min_observed_rating_delta_per_day_status
  is_anomaly_candidate: bool
```

Gate semantics:

- unconfigured gate -> `not_configured`;
- configured gate with missing/unusable evidence -> `unknown`;
- configured gate whose usable value meets threshold -> `pass`;
- configured gate whose usable value does not meet threshold -> `fail`.

Longitudinal gate details:

- `observed` has usable numeric delta and may pass/fail;
- `negative_revision` has usable numeric delta and therefore normally fails any non-negative minimum;
- `current_missing`, `no_prior_observation`, `interval_too_short` -> `unknown`.

Qualification rule:

```text
is_anomaly_candidate = true
IFF every configured gate == pass
```

`unknown` never silently qualifies.

When `anomaly_policy = null`, anomaly status is `disabled`, evaluations are empty, and the candidate queue is empty.

---

# 9. `analyst-directness-review-v1`

V1 reviews the semantic **direct-candidate tail only**. If repeated false negatives are discovered in adjacent/noise rows, the semantic thesis declaration must be corrected/versioned rather than silently overridden here.

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

Row:

```text
platform_listing_id
semantic_directness: "direct_candidate"
analyst_verdict: confirmed_direct | adjacent | not_direct | unresolved
reason_code: DirectnessReasonCodeV1
note: trimmed non-blank string | null
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

Allowed verdict/reason pairs:

```text
confirmed_direct:
  direct_mechanic_and_theme
  other

adjacent:
  theme_incidental
  mechanic_applies_to_other_object
  broader_multi_object_scope
  other

not_direct:
  theme_incidental
  mechanic_mismatch
  theme_mismatch
  mechanic_applies_to_other_object
  broader_multi_object_scope
  other

unresolved:
  insufficient_context
  other
```

`reason_code = other` requires `note != null`.

Other review invariants:

- reviewed listing exists in the bound semantic report;
- bound semantic row is exactly `direct_candidate`;
- row `semantic_directness` equals the bound semantic value;
- listing IDs are unique in the review artifact;
- `reviewed_at` is analyst input and never regenerated during rebuild;
- canonical review row order follows bound semantic-report listing order, not input-file order.

---

# 10. Competitor quality

```text
CompetitorQualityV1
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
semantic_source_observed_count
= semantic rows with source != null

semantic_source_missing_count
= raw union - semantic_source_observed_count

semantic_source_coverage_ratio
= semantic_source_observed_count / raw union

semantic_direct_candidate_share
= semantic_direct_candidate_count / raw union
```

`rejected_direct_false_positive_count` counts direct-candidate review verdicts `adjacent` or `not_direct`.

Manual review coverage denominator is semantic direct-candidate count. If there are zero direct candidates, coverage ratio is null and state is `no_direct_candidates`.

## 10.1 Query-surface quality

```text
QuerySurfaceQualityV1
  query_count
  members_seen_by_multiple_queries
  multi_query_member_share
  mean_pairwise_jaccard: float | null
  median_pairwise_jaccard: float | null
  queries: tuple[QueryContributionV1, ...]
  pairwise: tuple[PairwiseQueryOverlapV1, ...]
```

```text
QueryContributionV1
  query_text
  organic_member_count
  unique_contribution_count
```

`unique_contribution_count` is the count of comparable members whose organic search evidence includes this query and no other query in the thesis family.

```text
PairwiseQueryOverlapV1
  left_query
  right_query
  intersection_count
  union_count
  jaccard: float | null
```

Pairwise order follows query declaration combinations `(0,1), (0,2), ...`.

Mean/median use only numeric non-null pairwise Jaccard values and are null when no numeric pair exists.

These values describe search-surface coherence, not market size.

---

# 11. Per-thesis intelligence report

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

Invariants:

- traction order exactly equals frozen comparable member order;
- anomaly candidate IDs exactly equal evaluation rows with `is_anomaly_candidate=true`, ordered by the frozen anomaly queue order;
- prior artifact tuple is canonical section-4 order;
- review hash is null when no review is supplied;
- semantic report binds the exact current snapshot and exact target comparable;
- a supplied review binds this semantic report hash and the same thesis identity;
- no report row references a listing outside the thesis comparable set.

---

# 12. Cross-thesis comparison

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

```text
ThesisComparisonRow
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

Fresh/recent v1 window is exactly:

```text
listing_age_days <= 180.0
```

`recent_release_180d_share` denominator is listings in the thesis comparable with observed first-publication age. `recent_release_coverage_ratio` exposes that denominator coverage over the full thesis comparable.

Longitudinal observed coverage counts rows with status `observed` or `negative_revision`; `interval_too_short` is not usable velocity coverage.

```text
ListingMetricHighlightV1
  platform_listing_id
  title: string | null
  metric_name: rating_count | lifetime_ratings_per_day
  value: finite float
  observation_id: string | null
  status: "observed"
```

For equal metric values choose the earliest listing in frozen comparable order.

`best_adjacent_rating_count` uses semantic `adjacent_candidate` rows only. Adjacent evidence is never substituted for missing direct evidence.

No comparison field represents winner, recommendation, or project priority.

---

# 13. Intelligence artifact

Final create-only location convention:

```text
artifacts/intelligence/<suite_id>/<run_id>.zip
```

where `run_id` is the current bound experiment run ID.

Canonical members:

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

Artifact manifest version:

```text
thesis-intelligence-artifact-v1
```

It stores sorted member path/size/SHA-256 entries and excludes itself from its member list, following existing experiment-artifact create-only principles.

Canonical JSON/CSV/Markdown member bytes must rebuild identically from the same canonical suite declaration, verified current/prior experiment artifacts, method versions, and review artifacts.

Verification is member/hash based. ZIP container binary equality is not required unless implementation later freezes ZIP metadata explicitly.

---

# 14. Measurement-honesty invariants

The following are contract violations:

```text
calling lifetime_ratings_per_day a current growth rate
calling observed_rating_delta_per_day plays/day or DAU
silently flooring listing age to create a pace
using mutable ambient SQLite state during deterministic build
using a prior artifact without verifying/freezing its hash
silently ignoring a configured anomaly gate when evidence is missing
counting semantic direct_candidate as confirmed competitor truth
turning zero confirmed direct candidates into absolute market absence
using adjacent evidence as fallback for missing direct evidence
sorting comparison rows into an implied winner order
adding BUILD/WATCH/SKIP or an opportunity score to these v1 reports
```

If a requested output cannot be produced without violating these rules, the correct result is explicit missing/unknown evidence or a failed build, not an inferred substitute.
