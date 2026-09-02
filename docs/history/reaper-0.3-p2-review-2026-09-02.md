# Reaper 0.3 P2 Review — 2026-09-02

**Scope:** frozen current/prior experiment evidence -> age/pace/cohort traction features + observed rating deltas only.

**Verdict:** PASS after one review correction.

## Delivered contract

P2 introduces a deterministic `traction-features-v1` report over the P1 immutable artifact bindings.

Current evidence is derived only from:

```text
verified current experiment ZIP
-> AnalystSnapshotReport.created_at
-> AnalystMarketExportReport listing rows
```

Historical evidence is derived only from explicitly supplied and P1-verified prior experiment ZIPs.

No network access, ambient SQLite state, scheduler, schema migration, or fabricated time-window velocity was introduced.

## Age and lifetime pace

The reference time is exactly the current frozen snapshot `created_at`.

Frozen buckets are implemented as:

```text
0 <= age < 7      -> lt_7_days
7 <= age < 31     -> 7_30_days
31 <= age < 91    -> 31_90_days
91 <= age < 181   -> 91_180_days
181 <= age < 366  -> 181_365_days
age >= 366        -> over_365_days
```

Lifetime pace uses the exact elapsed-day denominator and requires `listing_age_days >= 1.0`.

```text
missing publication -> missing_first_published
0 <= age < 1 day    -> too_young
age >= 1 + missing ratingCount -> missing_rating_count
age >= 1 + observed ratingCount -> ratingCount / exact age days
```

There is no denominator floor and no conversion of missing evidence to zero.

## Suite-relative percentile

The age-bucket cohort is built across unique `platform_listing_id` values over the whole current suite scope.

A listing appearing in multiple thesis comparables participates once in the cohort.

For each bucket P2 exposes:

```text
member count
lifetime-pace observed count
coverage ratio
empirical-CDF percentile for rows with observed pace
```

The percentile is:

```text
count(observed bucket pace <= listing pace) / observed bucket pace count
```

Ties therefore receive the same percentile and the denominator remains visible.

## Review correction — explicit rating-count coverage

Initial P2 rows exposed `rating_count = null` honestly, but the roadmap explicitly requires rating-count coverage to be visible separately from numeric values.

The final P2 thesis set therefore exposes:

```text
rating_count_coverage.member_count
rating_count_coverage.observed_count
rating_count_coverage.missing_count
rating_count_coverage.coverage_ratio
```

This avoids forcing downstream analysis to infer evidence coverage from longitudinal or pace states.

## Longitudinal rating deltas

For one current listing, prior candidates come only from explicitly bound prior artifacts and only when their `rating_count` observation timestamp is strictly earlier than the current observation timestamp.

Selection is deterministic:

```text
latest eligible observed_at
-> if one candidate: select it
-> if same-time equal values: lexicographically smallest (artifact_sha256, observation_id)
-> if same-time conflicting values: fail closed
```

The artifact snapshot date does not substitute for the metric observation timestamp.

States are preserved explicitly:

```text
current_missing
no_prior_observation
interval_too_short
observed
negative_revision
```

For intervals shorter than one day the prior point and raw delta remain visible, but `observed_rating_delta_per_day` is unavailable.

Negative rating-count revisions remain negative and are not clamped or described as negative traffic.

## Determinism and provenance

The report binds:

```text
suite content hash
current experiment binding
canonically ordered prior experiment bindings
current snapshot reference time
per-thesis comparable identity
per-listing current observation identity
selected prior artifact + observation identity when available
report content hash
```

Thesis report rows preserve frozen comparable member order. Thesis sets preserve suite declaration order.

## Tests

Focused P2 tests cover:

- every frozen age-bucket boundary;
- no denominator flooring;
- suite-wide cross-thesis listing deduplication;
- cohort coverage and empirical-CDF percentile semantics;
- explicit rating-count coverage;
- no-history state;
- latest eligible prior selection;
- canonical prior artifact ordering independent of caller order;
- positive rating delta;
- negative revision;
- sub-day interval;
- equal-timestamp conflicting prior values;
- deterministic equal-timestamp/equal-value tie-break;
- equal/future prior observations being ineligible;
- missing current rating count never becoming zero velocity;
- non-integral rating count failing closed;
- report content-hash tampering.

## Quality gate

Final code head passed:

```text
ruff
strict mypy
full pytest
repository coverage >= 80%
```

## Scope guard

P2 does not implement:

```text
anomaly gate evaluation
anomaly queue ordering
manual directness review
competitor-set quality
cross-thesis comparison
CLI run/build/verify orchestration
package version bump
```

Those remain P3+.

**Review verdict: PASS. P2 is ready to merge.**
