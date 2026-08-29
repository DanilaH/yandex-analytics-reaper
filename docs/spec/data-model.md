# Production Data Model

This document owns the logical persistence model. Runtime/package boundaries are owned by `/ARCHITECTURE.md`; sequencing is owned by `/ROADMAP.md`.

## Data flow

```text
Sources
→ Raw immutable snapshots
→ Versioned source parsers
→ Source DTOs
→ Versioned normalizers
→ Domain observations
→ Operational normalized persistence
→ Lineage
→ Market state / taxonomy / derived features
→ Discovery / candidate dossiers
→ Backtests
→ Own-game calibration
```

## Operational storage choice

Phase 2 starts with SQLite as the operational normalized store for the private single-user collector. This is a deployment/maintenance choice, not part of the analytical semantics.

The logical model below must remain portable. A single versioned migration registry owns the SQLite schema. Parquet/DuckDB may later serve analytical scans/backtests; PostgreSQL is only justified if measured operational requirements outgrow SQLite.

## Identity

### `platform_listings`

Primary analytical identity during Yandex-only phases:

```text
id
platform
external_app_id
listing_url
developer_external_id
first_seen_at
last_seen_at
first_published_at
```

Identity fields (`id`, `platform`, `external_app_id`) are immutable once observed. Mutable latest-state metadata such as `listing_url` and current `developer_external_id` may only advance from an equal/newer observation timestamp; historical backfill must not regress current state.

### `games`

Optional canonical cross-platform identity:

```text
id
canonical_name
identity_status
created_at
```

A listing may have `game_id = null` until cross-platform resolution is actually needed. Do not make entity resolution a Yandex MVP dependency.

### Developers

Developer history is a first-class analytical entity:

```text
platform_developers
  id
  platform
  external_developer_id
  display_name
  first_seen_at
  last_seen_at

listing_developer_observations
  listing_id
  developer_id
  observed_at
```

Developer identity fields are immutable. The latest display name may only advance from an equal/newer observation timestamp. Listing/developer assignment observations are append-only by `(listing_id, observed_at)`; a conflicting developer for the same listing and observation timestamp is a data error rather than an overwrite.

Do not assume developer names/ownership are eternally static.

## Raw snapshots

Raw source facts are stored on the filesystem before interpretation. `RawSnapshotMetadata` contains:

```text
id
source_id
retrieved_at
request_key
request_context_json_redacted
content_location
content_hash
http_status
content_type
schema_fingerprint
```

No parser/normalizer version belongs in the raw snapshot record.

Snapshot IDs encode the UTC collection date and can be resolved deterministically by `(source_id, raw_snapshot_id)` back to immutable metadata and stored body. The operational SQLite store therefore does not need to duplicate raw snapshot bytes merely to support lineage.

## Parse runs

```text
parse_runs
  id
  raw_snapshot_id
  parser_name
  parser_version
  started_at
  completed_at
  status
  error
```

Parser output is a source-specific DTO. It is not a domain observation.

Where a source returns repeated game objects in alternative shapes, the parser preserves the **exact raw object path** on the DTO. Example Yandex paths:

```text
$.feed[0].widgets[2].data
$.feed[1].items[3]
$.games[7]
```

The normalizer must not reconstruct or guess this path later.

## Normalization

Use a technical observation envelope as the lineage anchor rather than duplicating every typed value inside a generic JSON payload.

```text
normalized_observations
  id
  source_id
  observation_type
  observed_at
  available_at
  retrieved_at
  normalizer_name
  normalizer_version
```

The envelope is persisted for numeric metric observations. A persisted metric requires `retrieved_at`; all stored temporal values must be timezone-aware and satisfy:

```text
observed_at <= available_at <= retrieved_at
```

when `available_at` is known.

Typed tables reference `normalized_observations.id`.

Examples:

```text
game_metric_observations
listing_state_observations
surface_exposures
search_results
```

## Field-level lineage

`FieldLineage` is an evidence-layer model produced by normalizers and persisted by storage. One domain observation may use multiple raw/source inputs.

```text
observation_lineage
  normalized_observation_id
  raw_snapshot_id
  source_field_path
  target_field_path
  transformation_name
  transformation_version
```

Example:

```text
$.games[1].gqRating
→ YandexGameNormalizer.yandex_games_rating@2
→ game_metric_observations.value_numeric
```

For Yandex feed/get-games card metrics, source object paths come from the parser, so the lineage distinguishes `feed[].widgets[].data`, `feed[].items[]`, and `games[]` instead of guessing the response shape. For HTML game pages, embedded-script locators are explicit (for example `$.__playPageData__.gameData.gqRating`) rather than pretending the HTML document itself has a JSON root.

Metric row + field-level lineage are written in the same SQLite transaction. Duplicate/conflicting source→target transformation records are errors and roll back the associated metric write.

A decision-relevant dossier value must eventually be traceable through derived feature → domain observation → lineage → raw snapshot metadata/body.

Legacy/coarse `EvidenceEnvelope.lineage_refs` may remain for non-field references, but they are not a substitute for `observation_lineage` when field-level provenance is available.

## Game metrics

`game_metric_observations` stores:

```text
observation_id
platform_listing_id
metric_name
period_start
period_end
value_numeric/value_text
provenance
measurement_kind
semantic_confidence
coverage_status
historical_availability
revision_status
uncertainty
missing_reason
```

The current metric writer supports finite numeric observed values. Boolean values and numeric-looking strings are rejected at the domain boundary rather than being coerced.

Metric observation identity is deterministic from source/listing/metric/time-window/retrieval/normalizer metadata. Rewriting the exact same observation is idempotent; supplying conflicting evidence/value for that same observation is an error rather than an overwrite. Metric batches are transactional.

A listing identity must exist before metrics referencing it can be persisted.

Do not attach contextual dimensions unless empirical evidence shows the metric itself varies by context.

## Listing-state observations

Track current/changed listing metadata such as:

```text
title
app_version
published_time
languages/platforms/orientation
leaderboard/purchase/product flags
ad-use metadata
status
status_reason
```

## Probe runs / exposure

```text
probe_contexts
probe_runs
probe_pages
surface_exposures
```

A probe run groups all pages belonging to one logical contextual observation.

`surface_exposures` stores listing ID, page/position/row/column, surface, and selection origin (`organic/sponsored/editorial/unknown`).

## Search discovery

```text
query_families
search_queries
search_probes
search_results
comparable_sets
comparable_set_members
```

`totalGamesCount` is stored as a search-supply observation, not competitor count.

## Taxonomy

```text
taxonomy_versions
classification_runs
game_classifications
taxonomy_label_registry
taxonomy_gold_set
themes
theme_aliases
```

Controlled labels are versioned. Theme entities remain extensible.

## Production assessment

Candidate-specific table; never store production burden as market taxonomy:

```text
candidate_production_assessments
  candidate_id
  assessment_version
  tooling_profile
  estimated_days_low/high
  burdens
  risks
  reusable_systems
  created_at
```

## External observations

External market/trend series use the same Evidence Model/time semantics as Yandex observations, including `available_at`, historical availability, revision status, and uncertainty.

## Platform policy regimes

```text
platform_policy_regimes
  platform
  effective_from/effective_to
  policy_version
  relevant rating/unpublish/featuring/moderation fields
  source_reference
  semantic_confidence
```

## Candidate decisions

```text
candidate_concepts
candidate_evidence
candidate_decisions
```

Decision records store decision version, validation status (`heuristic/backtest_validated/portfolio_calibrated`), reasons, unknowns, and WATCH review triggers.

## Backtesting

Store versioned BacktestSpec/run metadata, frozen feature sets, outcomes, censoring status, and failure reasons. Backtest records must preserve the exact decision `as_of` horizon and data availability rules.

## Own-game calibration

Freeze the dossier/prediction used before build, then store realized development cost and Yandex/economic outcomes. Calibration changes create new explicit policy/assessment versions; historical predictions are never rewritten.

## Schema drift

A schema fingerprint alone is insufficient. Phase 2 drift monitoring should include at least:

```text
field presence
field types
important nested shapes
missingness changes
parse failures
```

Do not silently auto-adapt source interpretations.
