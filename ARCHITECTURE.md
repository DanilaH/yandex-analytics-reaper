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
  experiments/    versioned replay/calibration evaluators over stored evidence
  ingestion/      application-owned collection/run/session orchestration
  normalizers/    source DTO → stable domain observation boundary
  schema_drift/   versioned raw-shape profiling/contracts/drift events
  sources/        source capability contracts
    yandex/        Yandex client + source DTO parsers/contracts
  storage/        raw snapshot + normalized operational persistence
  taxonomy/       draft taxonomy schema foundations
  cli.py          explicit local probes/debug/calibration interface
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

## Context/session boundary

Contextual Yandex feed/search collection has a session-preparation step before the paginated probe runner:

```text
requested ProbeContext
→ YandexSessionManager
→ prepared HTTP client + effective ProbeContext
→ YandexPaginatedProbeRunner
```

`YandexSessionManager` owns only HTTP session isolation/reuse and local cookie state. It does not parse responses or persist market observations.

Current mechanics:

```text
clean_anonymous
→ fresh client/cookie jar per logical run
→ no local state reused
→ session_instance_id = null

persistent_anonymous
→ source-specific local cookie jar loaded before the run
→ same anonymous profile updated after the run
→ one stable non-secret session_instance_id per local profile instance
→ effective context contains session instance ID + cookie-state fingerprint + profile age

authenticated_test
→ fail closed until an explicit credential provider is introduced
```

Persistent cookie files are **local runtime state**, not operational market persistence. They may contain raw cookie values because those values are required to reuse the anonymous HTTP profile. They must stay outside raw-snapshot metadata and SQLite analytical/operational tables and must never be committed. The operational context stores the session profile, stable non-secret session instance ID, one-way SHA-256 state fingerprint, and profile age.

`session_instance_id` identifies one local persistent profile cohort only. It is randomly generated, is not a Yandex user identity or credential, survives ordinary cookie churn, and changes when that local persistent profile is explicitly reset. The cookie fingerprint separately describes the state loaded at run start.

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
  ├→ contextual probe-page/run linkage for paginated feed/search surfaces
  ↓ normalizer(version)
Domain Observation + FieldLineage
```

For paginated Yandex feed/search collection, the application `ingestion` layer owns the complete run lifecycle:

```text
prepare session + effective context
→ collect page
→ persist raw
→ reject non-2xx
→ persist schema analysis
→ stop on breaking drift
→ parse source DTO
→ validate raw request/context/cursor identity
→ append ProbePage to ProbeRun
→ follow exact continuation tokens
→ persist COMPLETED / PARTIAL / FAILED terminal state
→ persist reusable anonymous session state when applicable
```

The CLI delegates session preparation and run lifecycle to ingestion services; it must not duplicate cookie/pagination/terminal-state business logic. A failed/partial run keeps the raw snapshot ID that caused the terminal condition when a response was actually received. If failure occurs before any response exists, terminal raw provenance remains absent rather than being invented.

If a probe fails and persistent-session state also cannot be saved, the probe/source error remains the primary exception and the state-save failure is secondary diagnostic context. A corrupt or incomplete persistent session fails closed rather than being silently reset into a different cohort.

Raw snapshots contain request/response facts and safe request context only. They are independent of parser, schema-analyzer, and normalizer versions so historical data can be reprofiled/reparsed/reinterpreted after implementation changes.

The filesystem raw store supports deterministic metadata and exact-body replay by `(source_id, raw_snapshot_id)`. Body replay rechecks that the resolved path stays under the configured raw root and that the body still matches the persisted SHA-256 content identity.

## Experiment/replay boundary

Calibration experiments consume already persisted evidence; they do not own collection. The first implementation is `experiments/feed_depth.py`.

```text
explicit ProbeRun IDs
→ load ProbeRun + ProbeContext + ordered ProbePages
→ replay immutable raw bodies
→ verify content hash
→ parse with the experiment-declared parser version
→ reconstruct ProbePage from raw request/context + parsed continuation data
→ require reconstructed page == stored page linkage
→ derive experiment observations
→ apply frozen decision policy
→ emit report
```

The experiment layer must reject or report ineligible evidence rather than repair it. It must not reinterpret a `partial`/`failed` collection as evidence for a shallower depth, and it must not silently select convenient runs from the operational store. Trial membership is explicit in the analysis invocation/report.

`feed-depth-v1` is intentionally scoped to `clean_anonymous / ru / desktop / desktop_other`. Session-profile stability and other context dimensions remain separate roadmap experiments. A legitimate source exhaustion before the configured ten-page maximum is not an operational failure; candidate depths beyond exhaustion saturate at the final available ranking.

Synthetic fixture tests validate the analyzer mechanics but are not empirical calibration evidence. The roadmap feed-depth item remains incomplete until the frozen minimum real-sample requirements are met and the report yields a recommendation.

## Schema drift

Schema monitoring observes source shape; it does **not** repair source changes or teach parsers to accept them automatically.

For JSON surfaces the current flow profiles normalized JSON paths, exact value types, parent/present counts, missingness ratios, root type, parse failures, and explicit source contracts. Each persisted analysis is versioned by analyzer + contract and is bound to the raw snapshot's exact SHA-256 content identity.

Temporal comparisons occur only inside a source-defined `comparison_scope_id`. Yandex scope construction keeps relevant request context while excluding volatile pagination-token values and volatile cookie-state/profile-age provenance, so desktop/mobile, session-profile classes, different persistent session instances, different search queries, and unrelated `get_games` cohorts keep meaningful boundaries without fragmenting baselines on normal cookie churn. A stable `session_instance_id` remains part of the comparison boundary; an explicit persistent-profile reset therefore starts a new baseline. Baselines are strictly earlier by `retrieved_at`; equal timestamps are not artificially ordered by snapshot IDs.

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
probe contexts
logical paginated probe runs
ordered probe pages + cursor-chain/raw-snapshot linkage
```

Probe contexts store safe session provenance, including the stable non-secret persistent-profile instance ID, but never secret session material. Persistent raw cookie values remain solely in the local runtime session directory.

Probe-page raw identity is unique by `(source_id, raw_snapshot_id)`, matching the filesystem raw-store identity boundary rather than assuming snapshot IDs are globally unique across sources.

Metric writes are idempotent for the same semantic observation and reject conflicting rewrites. A persisted metric requires an existing listing identity and explicit retrieval-time evidence.

Parquet/DuckDB should be introduced later for analytical scans/backtests when concrete query patterns require them. PostgreSQL should only replace the operational store if measured concurrency, scale, deployment, or query requirements justify running a database service.
