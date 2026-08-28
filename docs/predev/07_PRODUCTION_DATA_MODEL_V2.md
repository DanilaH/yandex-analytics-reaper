# Production Data Model & Architecture v2

## 1. Architecture

```text
Sources
  ↓
Raw immutable snapshots
  ↓
Versioned parsers
  ↓
Platform listings / normalized observations
  ↓
Lineage
  ↓
Taxonomy + market state
  ↓
Derived features
  ↓
Discovery / candidate dossiers
  ↓
Backtests
  ↓
Post-launch calibration
```

Start as a data system, not a dashboard. Initial stack: Python/httpx/pydantic/polars, then PostgreSQL/Parquet/DuckDB when normalized historical persistence is actually needed.

## 2. Platform-neutral identity

`games` stores canonical identity. `platform_listings` stores game ID, platform, external app ID, developer listing ID, URL, first/last seen, and first publication. Yandex IDs are not domain primary keys.

## 3. Source capabilities

Store sources separately from source_capabilities so providers are integrated capability-by-capability.

## 4. Raw snapshots

Raw snapshot fields:

```text
id
source_id
retrieved_at
request_key
request_context_json_redacted
content_location
content_hash
http_status
schema_hash
```

Raw snapshots contain no parser version. Sensitive request metadata is redacted before persistence.

## 5. Parsing

`parse_runs` stores raw snapshot, parser name/version, timing, status, and error. `normalized_observations` stores entity, type, time, payload, and normalizer version.

## 6. Many-to-many lineage

One normalized observation may combine multiple raw sources. `observation_lineage` maps observation ID to raw snapshot, field path, and transformation ID. Candidate evidence must trace through derived features and normalized observations back to raw snapshots.

## 7. Game metrics

`game_metric_observations` stores platform listing, source, metric, time/period, value, measurement kind, semantic confidence, coverage, point-in-time integrity, and lineage. Do not attach context dimensions unless metric variance by context is empirically proven.

## 8. Listing-state observations

Track title/developer/version/published time/languages/platforms/orientation, leaderboard/purchase/product flags, ad usage, status and status reason.

## 9. Exposure observations

`probe_contexts` includes language/device/platform/country/collector region/auth/session profile/cookie-state hash/profile age. `surface_probes` stores surface/context/time/request/coverage. `surface_exposures` stores listing position/page/row/column and organic/sponsored/editorial/unknown type.

## 10. Search discovery

Version query families. Search probes store result count and coverage; results store listing/page/position.

## 11. Taxonomy

Taxonomy versions have draft/validated/frozen status. Classifications store primary core loop, labels, confidence, evidence, and review status. Maintain a human gold set.

## 12. Production assessment

Candidate production assessments store assessment version, tooling profile, estimated day range, burdens, risks, and reusable systems. Do not store production burden in market taxonomy.

## 13. External observations

Generic metric observations carry provenance, measurement kind, semantic confidence, coverage, point-in-time integrity, uncertainty, and lineage.

## 14. Platform policy regimes

Track effective date range, policy version, rating threshold/formation/unpublish windows, New duration, ranking/moderation notes, source reference, and confidence.

## 15. Candidate research

Version candidate concepts, candidate evidence envelopes, and decisions. WATCH decisions include review time and trigger conditions.

## 16. Backtesting

Backtest runs explicitly store strict-point-in-time vs retrospective mode, feature/taxonomy versions, temporal windows, and metrics. Outcomes carry censoring status and failure reason.

## 17. Own-game calibration

Freeze release predictions before build, capture actual dev/moderation/traffic/retention/gqRating/revenue outcomes, and calculate market/production/economic prediction errors.

## 18. Schema drift

Compute schema hashes and field/type/missingness checks. Alert on removed target fields, type changes, new nested structure, missingness spikes, or unparseable responses. Do not silently auto-adapt.

## 19. MVP boundary

Do not initially build a full dashboard, realtime streaming, ClickHouse, large ML platform, auto-game generator, or complex orchestration. MVP means current Yandex market observation, normalized history, taxonomy gold-set workflow, candidate discovery, candidate dossier, and traceable BUILD/WATCH/SKIP.
