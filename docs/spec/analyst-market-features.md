# Analyst Market Features

`analyst-market-features-v1` is the first transparent derived layer over a frozen
`analyst-snapshot-v1` plus its matching `analyst-market-export-v1`.

It exists to make concrete comparable sets easy to inspect without introducing an opportunity
score, a market model, or a BUILD / WATCH / SKIP policy.

## Input boundary

The builder consumes exactly two already-frozen artifacts:

```text
AnalystSnapshotReport
AnalystMarketExportReport
```

The export must bind the exact snapshot `content_hash`, effective context, search depth, and rich
metadata raw-snapshot identities. The feature builder does not access the network, raw store, or
SQLite.

`reference_time` is the frozen `snapshot.created_at`. Release age must not be reconstructed from
wall-clock execution time or from the latest observation timestamp.

The report stores both input content hashes and has its own deterministic content hash. Replaying
the same two artifacts under the same v1 contract therefore produces the same feature artifact.

## Comparable-set denominator

Every feature block is computed independently for one frozen comparable set.

```text
member_count
= count of unique organic members in the frozen yandex_search_union_v1 set
```

This is **observed organic union size at the explicit frozen search depth**, not a canonical
competitor count and not an estimate of the entire Yandex market.

A listing that belongs to multiple comparable sets participates independently in each set's
features.

## Query supply

`totalGamesCount` remains a query-level source observation. It is never summed across query-family
variants and never substituted for comparable-set size.

For every frozen search run the feature report preserves page-ordered observations:

```text
query_text
probe_run_id
page_index
raw_snapshot_id
total_games_count | source_missing
```

It additionally reports the observed values, distinct observed values, and whether the observed
pages were internally consistent. No average or combined cross-query market-size estimate is
created.

## Numeric distributions

The v1 numeric summaries are used for:

```text
gqRating
player rating
ratingCount
first-published age in days
```

Every distribution contains explicit coverage:

```text
total_count
observed_count
missing_count
coverage_ratio
```

Missing values are excluded from numeric summaries; they are never converted to zero.

For observed values the report emits:

```text
minimum
p25
median
p75
maximum
mean
```

`p25`, `median`, and `p75` use deterministic linear interpolation over the sorted observed values.
For percentile fraction `p` and `n` observations:

```text
index = (n - 1) * p
```

If the index falls between two observations, the result is linearly interpolated between them.
This is descriptive statistics only; no percentile is interpreted as a quality threshold.

## First publication and recent-release windows

Release age uses only snapshot-scoped `first_published_at`, which comes from Yandex
`get_games.firstPublished`. It remains distinct from game-page `publishedTime` / update history.

V1 includes cumulative descriptive windows:

```text
<= 30 days
<= 90 days
<= 180 days
<= 365 days
```

Each window reports listing count and share among listings with observed `first_published_at`.
Coverage remains separate, so a niche with 20% publication-date coverage cannot appear equivalent
to one with 100% coverage merely because their observed recent-release shares match.

The windows are descriptive conveniences, not decision-policy thresholds. A source publication
timestamp after `snapshot.created_at` fails closed rather than producing a negative age.

## Organic exposure summaries

Search and feed exposure remain contextual evidence, not game metrics.

For each comparable set the report summarizes **organic** exposure only:

```text
evidence_available
run_count
exposure_count
exposed_member_count
unexposed_member_count
member_coverage_ratio
```

Search evidence is available by construction for `yandex_search_union_v1`. Repeated appearances
remain repeated exposure observations while `exposed_member_count` is unique by listing.

Feed evidence is available only when the frozen analyst snapshot actually contains feed runs.
Therefore:

```text
feed not collected
→ evidence_available = false
→ member_coverage_ratio = null

feed collected but no comparable member appeared
→ evidence_available = true
→ member_coverage_ratio = 0
```

Sponsored search/feed rows remain in `analyst-market-export-v1` for inspection but do not
contribute to these organic exposure summaries.

## Developer composition

Developer concentration uses snapshot-scoped `developer_id` only when it is observed.

The report includes:

```text
developer-ID coverage
distinct observed developer count
largest developer listing count / share
all observed developer groups sorted by listing count then developer ID
```

Each group keeps all distinct observed snapshot-scoped developer names. This avoids silently
choosing one display name when the same developer ID is associated with multiple names in the
frozen evidence.

Shares use the count of listings with observed developer IDs as their denominator. Missing
developer IDs remain explicit through coverage and are not grouped into a fabricated "unknown
developer" entity.

## Evidence-honesty boundary

`analyst-market-features-v1` does not infer or estimate unavailable competitor:

```text
DAU
retention
playtime
CTR
revenue
ARPDAU
```

It also does not:

```text
rank niches
weight signals
normalize features into one score
apply production feasibility
produce BUILD / WATCH / SKIP
claim taxonomy validation
claim collection parameters are empirically optimal
```

Those concerns belong to later milestones. M1.3 is complete when these transparent current-state
features are reproducibly available for the real M1.4 analyst pilot.
