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

## Representative aggregate trace

M1.4 requires representative aggregate traceability, not a second implementation of every M1.3 statistic. V1 therefore records exactly one deterministic representative trace per comparable set.

Selection priority is:

```text
rating_count
→ yandex_games_rating
→ player_rating
→ first_published_age_days
```

The first field with observed coverage is used. A comparable set with none of these fields observed does not pass the real pilot verifier; that is treated as a practical-analysis blocker.

Each representative trace stores:

```text
set_id / set_version
feature_name
coverage
reported_median
recomputed_median
contributing listing IDs
source values
numeric values used for the median
observation IDs
raw snapshot IDs
source field paths
normalizer name/version
```

The verifier recomputes the median independently from the listing-level contributions and requires it to match the frozen feature report.

If `first_published_age_days` is selected, the numeric age is derived again from the exported `firstPublished` timestamp and frozen `snapshot.created_at`. A publication timestamp after snapshot time fails closed.

This narrow trace is intentional. The feature layer remains the owner of full min/p25/median/p75/max/mean distributions; the pilot verifier proves one representative aggregate per niche without duplicating the whole analytical implementation.

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

Passing `analyst-pilot-verification-v1` proves only that the real pilot artifact chain is internally reproducible and that representative aggregates can be traced back to immutable evidence.

It does **not** prove:

```text
that query-derived peers are validated gameplay comparables
that collection depth/session/cadence is empirically optimal
that taxonomy is validated
that any niche is commercially attractive
that unavailable DAU/retention/playtime/revenue metrics exist
```

The `START ANALYSIS` gate is crossed only after the verifier passes on real Yandex data **and** the practical human review finds no blocker to using the workflow for actual niche comparison.