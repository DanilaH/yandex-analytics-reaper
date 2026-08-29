# Analyst Market Export

`analyst-market-export-v1` is the supported read/export boundary for one frozen `analyst-snapshot-v1`. It exists so current-market analysis does not require direct SQLite inspection and cannot silently consume observations collected after the analyst snapshot was frozen.

The export is descriptive evidence, not an opportunity score or a market model. Transparent aggregates belong to the next feature layer.

## Reproducibility boundary

The input is a validated `AnalystSnapshotReport`. The exporter revalidates the report and the immutable rich-metadata raw snapshots/content hashes that it binds.

For normalized listing state, metrics, and update metadata, an observation is eligible only when its required field lineage points to rich-metadata raw snapshots frozen into that analyst snapshot. A newer observation already present in SQLite must not replace a value in an older frozen export.

The export contains no wall-clock `generated_at`. Its `content_hash` is computed from canonical deterministic JSON content, so replaying the same frozen evidence with the same code contract produces the same export identity.

## Listing rows

One row is emitted for every listing in the snapshot's comparable sets. Missing rich metadata does not remove the listing.

Current v1 fields include:

```text
platform_listing_id
external_app_id
canonical_url
comparable_set_ids
title
developer_id
developer_name
first_published_at
app_version
published_at
languages
supported_platforms
orientation
cloud_save
leaderboards
purchases_enabled
has_products
rewarded_ads
fullscreen_ads
sticky_ads
yandex_games_rating
player_rating
rating_count
```

Each source-observed listing/metric field is represented as a resolved value:

```text
value
missing_reason
evidence
```

An observed value has an evidence reference containing the normalized observation ID, observation/retrieval timestamps, raw snapshot IDs, exact source field paths, and normalizer version. An unavailable value is `null` with `missing_reason = not_observed`; it is never silently converted to zero, `false`, or an empty string.

`developer_name` is stored in the listing-state observation rather than read from the mutable current developer identity. `first_published_at` comes from Yandex `get_games.firstPublished` and remains distinct from game-page `published_at`, which comes from `publishedTime`.

## Metrics and update metadata

The current listing table exports the supported normalized values:

```text
yandex_games_rating
player_rating
rating_count
```

Listing update observations are exported separately with:

```text
app_version
source_published_at
raw_snapshot_ids
source_field_paths
```

A metric/update observation with no field lineage is not eligible for a snapshot-scoped export. If a normalized observation depends on multiple raw snapshots, its full lineage must remain inside the frozen rich-metadata snapshot set; the exporter must not keep only an in-scope subset and present it as complete provenance.

## Comparable membership provenance

Each comparable-set membership row preserves the construction identity plus direct source provenance:

```text
set_id / set_version
member_ordinal
platform_listing_id
query_family_id / query_family_version
source_queries
probe_run_ids
raw_snapshot_ids
source_object_paths
```

This is redundant by design with search-exposure rows. A membership artifact should remain independently inspectable without requiring a join merely to discover which exact query/run/raw evidence admitted the member.

## Search supply

Search `totalGamesCount` is exported per query/run/page as a **query-supply observation**.

It is not:

```text
a canonical competitor count
safe to sum across query variants
proof that every returned game is a gameplay comparable
```

When the source omits `totalGamesCount`, the row remains present and records `missing_reason = source_missing`. Missing supply is not represented as zero.

## Feed and search exposure

Exposure evidence is intentionally separate from game metrics.

Search exposure rows represent organic membership evidence from the frozen search-derived comparable set and preserve exact query/run/page/raw/source-object provenance.

Feed exposure rows replay only feed runs frozen into the analyst snapshot and preserve:

```text
platform_listing_id
probe_run_id
page_index
raw_snapshot_id
source_object_path
organic_feed | sponsored_feed
row / column when observed
```

Sponsored feed cards are not converted into organic evidence.

## JSON and CSV artifacts

The supported operator command is:

```bash
yandex-reaper-analyst export-snapshot \
  <analyst-snapshot-report.json> \
  --report <analyst-market-export.json> \
  --csv-dir <new-directory> \
  --output data/raw
```

The JSON report is create-only. The optional CSV directory is also create-only and contains:

```text
listings.csv
comparable_memberships.csv
update_observations.csv
search_supply.csv
search_exposures.csv
feed_exposures.csv
```

The JSON report is the lossless evidence-bearing artifact. The CSV files are convenience tables for manual inspection; the flat `listings.csv` summarizes values/missing fields while full per-field evidence references remain in JSON.

## Scope boundary

`analyst-market-export-v1` does not compute distributional features, coverage percentages, developer concentration, opportunity heuristics, or BUILD/WATCH/SKIP decisions. Those are derived analytical layers and must retain traceability to this export/frozen snapshot rather than being folded into the raw read boundary.
