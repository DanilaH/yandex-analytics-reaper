# Analyst Pilot Verification

## Status

`analyst-pilot-verification-v1` is the offline audit artifact for the real M1.4 analyst pilot.

It does **not** make a synthetic fixture count as a real pilot. It exists so that, once real Yandex evidence has been collected on an operator machine, the final `START ANALYSIS` review does not depend on ad-hoc SQLite inspection or unverifiable manual arithmetic.

## Inputs

The verifier consumes exactly three frozen analyst artifacts plus the local immutable raw store:

```text
AnalystSnapshotReport
AnalystMarketExportReport
AnalystMarketFeaturesReport
FilesystemRawSnapshotStore
```

The three JSON artifacts must form one exact content-hash chain:

```text
snapshot.content_hash
        ↓
market_export.snapshot_content_hash
        ↓
market_features.snapshot_content_hash

market_export.content_hash
        ↓
market_features.market_export_content_hash
```

The feature `reference_time` must remain the snapshot `created_at`, and the provisional collection-parameter status must be unchanged across all artifacts.

## Real-pilot scope guards

A successful v1 pilot verification requires:

```text
at least 2 comparable sets
at least 2 distinct query_family_id values
at least 1 traceable quantitative rich-metadata feature in every comparable set
```

Two versions of the same query family do not satisfy the two-niche pilot requirement.

The verifier does not decide whether a query family is a commercially attractive niche. It only prevents the technical pilot from being satisfied by duplicate market questions.

## Fresh feature derivation

The supplied `AnalystMarketFeaturesReport` is not trusted merely because its hash is internally valid.

The verifier runs the public feature builder again:

```text
snapshot + market export
→ AnalystMarketFeatureBuilder
→ freshly derived feature report
→ exact equality with supplied feature report
```

Any difference fails closed.

## Aggregate traces

For every comparable set, the verifier traces every available one of:

```text
yandex_games_rating
player_rating
rating_count
first_published_age_days
```

A trace contains the feature distribution plus every contributing listing-level value:

```text
platform_listing_id
source_value
derived_numeric_value
observation_id
raw_snapshot_ids
source_field_paths
normalizer_name
normalizer_version
```

The verifier independently recomputes:

```text
minimum
p25
median
p75
maximum
mean
```

from the trace contributions and requires them to match the feature report.

`first_published_age_days` is derived again from the exported `firstPublished` timestamp and the frozen snapshot time. A publication timestamp after snapshot time fails closed.

A comparable set with no traceable quantitative rich-metadata feature does not pass the real pilot verifier. That condition is treated as a practical-analysis blocker rather than silently producing an empty proof.

## Raw-evidence replay

The verifier resolves every raw snapshot referenced by the pilot through `FilesystemRawSnapshotStore` and calls `get_body`, which rechecks the persisted content hash.

The audit covers:

```text
all rich-metadata raw snapshots frozen by the snapshot
all feed pages frozen by snapshot feed-run bindings
all search raw snapshots referenced by comparable membership
all search-supply raw snapshots
all search/feed exposure raw snapshots
all normalized listing/update evidence raw references
```

Request-key ownership also fails closed:

```text
search evidence → catalogue.search
feed evidence   → catalogue.feed
rich evidence   → the exact request_key frozen by AnalystSnapshotReport
```

A single raw snapshot cannot be claimed simultaneously by incompatible request keys.

Normalized listing/update evidence may reference only the rich-metadata raw snapshots frozen by the analyst snapshot. It cannot silently reach into a newer raw response that was collected after the snapshot.

The verification report stores raw snapshot IDs, not the local filesystem path. Moving the same immutable raw workspace to another machine therefore does not change the report content hash.

## Machine-detected limitations

The verifier records mechanical limitations that are already visible in the frozen artifacts, including:

```text
provisional/un-calibrated collection parameters
provisional search-derived comparable-set semantics
feed not collected
per-field missingness by comparable set
missing or inconsistent totalGamesCount observations
```

This list does not replace the human M1.4 review. Real source behavior may reveal additional usability or interpretation limitations that must be recorded separately before the `START ANALYSIS` gate is closed.

## Interpretation boundary

Passing `analyst-pilot-verification-v1` proves only that the real pilot artifact chain is internally reproducible and traceable to immutable raw evidence.

It does **not** prove:

```text
that query-derived peers are validated gameplay comparables
that collection depth/session/cadence is empirically optimal
that taxonomy is validated
that any niche is commercially attractive
that unavailable DAU/retention/playtime/revenue metrics exist
```

The `START ANALYSIS` gate is crossed only after the verifier passes on real Yandex data **and** the practical human review finds no blocker to using the workflow for actual niche comparison.