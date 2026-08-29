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
Schema-drift observation + versioned source parsers
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
  evidence/       evidence semantics, uncertainty, field lineage
  normalizers/    source DTO → stable domain observation boundary
  schema_drift/   versioned raw-shape profiling/contracts/drift events
  sources/        source capability contracts
    yandex/        Yandex client + source DTO parsers/contracts
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
  ↓ schema profile/contract where applicable
Raw shape + drift events
  ↓ parser(version)
Source DTO + exact source object path where applicable
  ↓ normalizer(version)
Domain Observation + FieldLineage
```

Raw snapshots contain request/response facts and safe request context only. They are independent of parser, schema-analyzer, and normalizer versions so historical data can be reprofiled/reparsed/reinterpreted after implementation changes.

The filesystem raw store supports deterministic metadata lookup by `(source_id, raw_snapshot_id)`, so a lineage record can be resolved back to immutable snapshot metadata and the exact stored body without a separate raw-snapshot database index.

## Schema drift

Schema monitoring observes source shape; it does **not** repair source changes or teach parsers to accept them automatically.

For JSON surfaces the current flow profiles normalized JSON paths, exact value types, parent/present counts, missingness ratios, root type, parse failures, and explicit source contracts. Each persisted analysis is versioned by analyzer + contract and is bound to the raw snapshot's exact SHA-256 content identity.

Temporal comparisons occur only inside a source-defined `comparison_scope_id`. Yandex scope construction keeps relevant request context while excluding volatile pagination-token values, so desktop/mobile, different search queries, and unrelated `get_games` cohorts cannot create false drift against each other. Baselines are strictly earlier by `retrieved_at`; equal timestamps are not artificially ordered by snapshot IDs.

Breaking contract drift stops semantic interpretation **after raw persistence**. Informational/warning drift is recorded without blocking the probe. Parser failures are separate breaking events.

The generic structural profiler currently covers the JSON `feed`, `search`, and `get_games` surfaces. The raw `game.page` response is HTML; it currently has parser-failure monitoring for `__playPageData__`, not generic JSON structural profiling over the HTML body.

## Lineage

Decision-relevant values are reconstructable through:

```text
candidate evidence
→ derived feature
→ domain observation
→ field-level normalization lineage
→ exact source field path
→ raw snapshot metadata/body
```

`FieldLineage` belongs to the evidence layer, not storage. Normalizers create lineage because they own source-field interpretation; storage only persists it.

For Yandex card/detail metrics, parsers preserve the exact raw object path, for example:

```text
$.feed[0].widgets[2].data
$.feed[1].items[3]
$.games[7]
```

The normalizer appends the exact metric field (for example `.gqRating`) rather than guessing which response shape produced the DTO.

Metric persistence and its lineage write share one SQLite transaction. A lineage conflict therefore rolls back the associated metric write instead of leaving partially traceable evidence.

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

Collectors return raw responses. Yandex schema contracts/scopes own source-specific structural expectations and comparison boundaries. Parsers own Yandex response-shape interpretation and preserve exact source object paths needed for lineage. Yandex normalizers convert parsed source DTOs into stable domain listing-state and metric observations plus field-level lineage.

## Persistence boundary

Raw responses remain immutable filesystem snapshots.

Phase 2 uses SQLite as the initial **operational normalized store** because the tool is private/single-user, collection is batch-oriented, and the current workload does not justify a database service. The storage contracts remain domain-oriented so this is not a commitment to SQLite as a permanent analytical backend.

A single versioned SQLite migration registry owns the operational schema. Independent stores must not maintain competing `PRAGMA user_version` schemes.

SQLite currently owns:

```text
platform listing identities
platform developer identities
listing ↔ developer observation history
normalized numeric metric observations
metric observation/evidence envelopes
normalizer name/version used for persisted metrics
field-level observation lineage
versioned schema observations / field profiles / drift events
```

Metric writes are idempotent for the same semantic observation and reject conflicting rewrites. A persisted metric requires an existing listing identity and explicit retrieval-time evidence.

Probe runs and other historical state are added by their explicit Phase 2 roadmap tasks rather than being hidden inside metric/lineage/schema persistence.

Parquet/DuckDB should be introduced later for analytical scans/backtests when concrete query patterns require them. PostgreSQL should only replace the operational store if measured concurrency, scale, deployment, or query requirements justify running a database service.
