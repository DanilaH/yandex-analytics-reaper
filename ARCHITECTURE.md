# Architecture

`ARCHITECTURE.md` owns code/runtime boundaries. Implementation sequencing belongs to `ROADMAP.md`; analytical semantics belong to `docs/spec/`.

## System boundary

```text
Sources
  ↓
CollectedResponse
  ↓
Raw immutable snapshots
  ↓
Versioned source parsers
  ↓
Source DTOs
  ↓
Versioned normalizers
  ↓
Platform-neutral domain observations
  ↓
Operational normalized persistence
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

The parser answers **what the source said**. The normalizer answers **what that source value means in our domain model**. Source DTOs must not leak into analytics/domain layers.

## Package layout

```text
src/yandex_analytics_reaper/
  candidates/     candidate/decision primitives
  domain/         platform-neutral entities and observations
  evidence/       evidence semantics and uncertainty
  normalizers/    source DTO → stable domain observation boundary
  sources/        source capability contracts
    yandex/        Yandex client + source DTO parsers
  storage/        raw snapshot + normalized operational persistence
  taxonomy/       draft taxonomy schema foundations
  cli.py          explicit local probes/debug interface
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

A provider may implement only a subset. A new official/third-party source replaces only the capabilities it actually supplies.

## Raw-first ingestion

Collection produces a `CollectedResponse`. Persist it before any source interpretation:

```text
CollectedResponse
  ↓ persist
RawSnapshotMetadata + exact body
  ↓ parser(version)
Source DTO
  ↓ normalizer(version)
Domain Observation
```

Raw snapshots contain request/response facts and safe request context only. They are independent of parser and normalizer versions so historical data can be reparsed/reinterpreted after implementation changes.

## Lineage

Decision-relevant values must be reconstructable through:

```text
candidate evidence
→ derived feature
→ domain observation
→ normalization lineage
→ source DTO/raw field
→ raw snapshot
```

Lineage is many-to-many: one domain observation may combine multiple raw/source observations.

## Identity

`PlatformListing` is the primary analytical identity during Yandex-only phases:

```text
platform = yandex_games
external_app_id = <appID>
```

`Game` exists as a platform-neutral canonical identity, but cross-platform entity resolution is deliberately optional until cross-market enrichment requires it. Do not build a matching engine during Yandex market-state work.

## Evidence

Do not use one confidence grade. Evidence semantics are owned by `docs/spec/evidence-model.md`.

Core independent dimensions include:

```text
provenance
measurement_kind
semantic_confidence
coverage
historical_availability
revision_status
uncertainty
```

Freshness is computed at read/decision time from timestamps; it is not an immutable stored evidence property.

## Yandex adapter

The current Yandex adapter has three proven current capabilities:

```text
recommendation/feed exposure
search discovery
rich game metadata
```

Collectors return raw responses. Parsers own Yandex response-shape interpretation. Yandex normalizers convert parsed source DTOs into stable domain listing-state and metric observations.

## Persistence boundary

Raw responses remain immutable filesystem snapshots.

Phase 2 uses SQLite as the initial **operational normalized store** because the tool is private/single-user, collection is batch-oriented, and the current workload does not justify a database service. The storage contract remains domain-oriented so this is not a commitment to SQLite as a permanent analytical backend.

SQLite currently owns:

```text
platform listing identities
platform developer identities
listing ↔ developer observation history
```

Metric observations, observation envelopes/field-level lineage, probe runs, and other historical state are added by their explicit Phase 2 roadmap tasks rather than hidden inside the identity store.

Parquet/DuckDB should be introduced later for analytical scans/backtests when concrete query patterns require them. PostgreSQL should only replace the operational store if measured concurrency, scale, deployment, or query requirements justify running a database service.
