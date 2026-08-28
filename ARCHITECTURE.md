# Architecture

## System boundary

```text
Sources
  ↓
Raw immutable snapshots
  ↓
Versioned parsers
  ↓
Normalized platform-neutral observations
  ↓
Lineage
  ↓
Market state / taxonomy / derived features
  ↓
Opportunity discovery + candidate dossiers
  ↓
BUILD / WATCH / SKIP
  ↓
Own release outcomes
  ↓
Calibration
```

## Package layout

```text
src/yandex_analytics_reaper/
  candidates/     candidate/decision primitives
  domain/         platform-neutral entities and observations
  evidence/       evidence semantics and uncertainty
  sources/        source capability contracts
    yandex/        current Yandex implementation
  storage/        immutable raw storage
  taxonomy/       taxonomy schema foundations
  cli.py          explicit local probes only
```

## Source capability architecture

Analytics depends on capabilities, not source brands:

```text
CatalogMetadataProvider
SearchDiscoveryProvider
RecommendationExposureProvider
HistoricalMetricsProvider
StatusHistoryProvider
MediaProvider
TrendProvider
```

A provider may implement only a subset.

## Raw-first ingestion

HTTP/source collection produces a `CollectedResponse`.

The response is written to `RawSnapshotStore` first. Only then may a parser normalize it.

```text
CollectedResponse
  ↓ persist
RawSnapshotMetadata
  ↓ parser(version)
Normalized observation
```

This lets us reparse historical raw data after schema/parser changes.

## Identity

`Game` is platform-neutral.

A Yandex app is a `PlatformListing` identified by:

```text
platform = yandex_games
external_app_id = <appID>
```

Future Steam/mobile listings can map to the same canonical game without changing the core model.

## Evidence

Do not use one confidence grade.

Decision-relevant evidence carries independent dimensions:

```text
provenance
measurement_kind
semantic_confidence
freshness
coverage
point_in_time_integrity
uncertainty
```

## Yandex adapter

The current public adapter implements three proven capabilities:

```text
feed exposure
search discovery
rich game metadata
```

The adapter returns raw responses; parsers own Yandex-specific schema interpretation.

## Persistence roadmap

Phase 1 uses filesystem raw snapshots only.

PostgreSQL/Parquet/DuckDB are introduced when normalized historical persistence begins. Do not add them merely to match an architecture diagram.
