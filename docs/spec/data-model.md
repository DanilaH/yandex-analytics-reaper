# Production Data Model

This document owns the logical persistence model. Runtime/package boundaries are owned by `/ARCHITECTURE.md`; sequencing is owned by `/ROADMAP.md`.

## Data flow

```text
Sources
→ Raw immutable snapshots
→ Versioned schema observations/contracts where applicable
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
method
url
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

A persisted semantic observation requires `retrieved_at`; all stored temporal values must be timezone-aware and satisfy:

```text
observed_at <= available_at <= retrieved_at
```

when `available_at` is known.

Typed tables reference `normalized_observations.id`.

Examples:

```text
game_metric_observations
listing_update_observations
listing_status_observations
listing_media_observations
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

For Yandex feed/get-games card metrics and listing histories, source object paths come from the parser, so lineage distinguishes `feed[].widgets[].data`, `feed[].items[]`, and `games[]` instead of guessing the response shape. For HTML game pages, embedded-script locators are explicit (for example `$.__playPageData__.gameData.gqRating`) rather than pretending the HTML document itself has a JSON root.

Metric rows and listing-history bundles write their typed data, evidence, and field lineage transactionally. Duplicate/conflicting source→target transformation records are errors and roll back the associated semantic write.

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

## Listing update/status/media histories

`listing-histories.md` owns the semantic rules. The logical model deliberately separates update metadata, availability/status, and media-manifest observations instead of overloading one nullable listing-state row.

Shared evidence dimensions live in:

```text
listing_history_evidence
  observation_id
  provenance
  measurement_kind
  semantic_confidence
  coverage_status
  historical_availability
  revision_status
  uncertainty_json
  lineage_refs_json
```

Typed histories are:

```text
listing_update_observations
  observation_id
  platform_listing_id
  app_version
  source_published_at

listing_status_observations
  observation_id
  platform_listing_id
  status
  status_reason

listing_media_observations
  observation_id
  platform_listing_id
  manifest_hash
```

`source_published_at` preserves Yandex `publishedTime` without claiming it is a general `updated_at`. The v1 status history stores only directly observed public presence as `published`, with provenance distinguishing catalogue metadata from game-page presence. Request omission is not persisted as a status until a future batch path can prove exact requested IDs against the same successful immutable response. Transport failure is likewise not a listing status.

Media history stores a canonical SHA-256 fingerprint rather than copying the opaque Yandex media DTO into the platform-neutral schema. `YandexGetGamesParser@4` distinguishes missing/non-object media (`None`) from a present empty object (`{}`). The raw manifest remains recoverable through required field lineage.

Every persisted history item requires at least one field-lineage row. One history bundle is transactional across the normalized envelope, evidence, typed row, and lineage. Observation identity excludes the observed value, so an identical replay is idempotent while a conflicting value or evidence envelope under the same identity is rejected.

History readers are ordered by `observed_at`, `retrieved_at`, and observation ID and support an `as_of` bound on observed time. Missing newer rows mean “not observed more recently,” not “known unchanged.” Readers fail closed on a wrong stored observation type, missing history evidence, or missing field lineage.

## Probe runs / exposure

`probe_contexts` deduplicates the **effective observation context actually opened for the run** by deterministic canonical identity:

```text
probe_contexts
  id
  language
  device_type
  platform
  country_observed
  collector_region
  session_profile
  session_instance_id
  cookie_state_hash
  profile_age_days
```

Session provenance semantics:

```text
clean_anonymous
→ session_instance_id = null
→ cookie_state_hash = null
→ profile_age_days = 0
→ no cookie state is reused

persistent_anonymous
→ session_instance_id = stable non-secret identifier for one local profile instance
→ cookie_state_hash = one-way fingerprint of the cookie jar loaded at run start
→ profile_age_days = whole days since the local anonymous profile was created
→ the raw cookie jar remains local runtime state and is never stored in this table

authenticated_test
→ reserved for an explicitly configured test credential/profile provider
→ current collector does not create this context by silently falling back to anonymous
```

`session_instance_id` is cohort provenance, not a Yandex account/user identity or credential. It remains stable while the same local persistent profile evolves and changes after an explicit profile reset, preventing pre/post-reset runs from being silently grouped as one persistent cohort. Legacy persisted `probe_contexts` migrate with this field as `null`; newly collected persistent runs receive a non-null instance ID from the session manager.

`cookie_state_hash` is state provenance, not a credential or user identity. Raw cookie/token values are forbidden in `probe_contexts`, raw snapshot metadata, and analytical tables. Persistent cookie material lives only in the local ignored runtime session directory needed to reproduce that anonymous HTTP profile.

`probe_runs` stores one logical paginated feed/search observation:

```text
probe_runs
  id
  source_id
  request_key
  probe_kind
  context_id
  query_text
  requested_page_limit
  started_at
  completed_at
  status
  error
  error_raw_snapshot_id
```

`query_text` is required for search and absent for recommendation-feed runs. Terminal states are `completed`, `partial`, and `failed`; a running run has no completion/error metadata. `error_raw_snapshot_id` identifies the persisted raw response that caused a terminal error when one exists and remains null for failures that occur before a response is available.

`probe_pages` stores the ordered raw pages of the run:

```text
probe_pages
  run_id
  page_index
  source_id
  raw_snapshot_id
  retrieved_at
  request_page_id
  request_rtx_reqid
  response_next_page_id
  response_rtx_reqid
  has_next_page
```

Pages must be contiguous from zero. Page 0 has no request continuation tokens. Later pages must consume exactly the prior page's emitted continuation values; no page may follow source exhaustion or a previous page that omitted required continuation tokens. Retrieval timestamps cannot move backwards.

Raw-page assignment is unique by `(source_id, raw_snapshot_id)`. The same generated snapshot ID may exist under a different source identity, but one raw response within a source cannot be assigned to multiple logical probe pages.

A `completed` run must contain at least one page and either reach its requested page limit or end on source exhaustion. A `partial` run contains at least one valid page plus an error. A `failed` run contains zero valid pages plus an error.

`surface_exposures` will store listing ID, page/position/row/column, surface, and selection origin (`organic/sponsored/editorial/unknown`) in its later roadmap task.

## Search discovery

Query-family declarations are immutable/versioned operational inputs:

```text
query_family_versions
  family_id
  version
  label
  source_id
  language
  created_at

query_family_members
  family_id
  version
  ordinal
  query_text
  variant_kind
```

`(family_id, version)` identifies one frozen declaration. Member `ordinal` preserves exact order; exact query text is unique within the version. One seed must exist at ordinal 0. An identical rewrite is idempotent, while different content under an existing family/version is a persistence conflict rather than an overwrite.

Existing search `probe_runs.query_text` remains the exact request text actually sent. Query-family execution provenance must bind runs to an exact declared family/version and exact member text; it must not infer membership fuzzily.

The first persisted comparable-set construction is `yandex_search_union_v1`:

```text
comparable_set_versions
  set_id
  version
  construction_method
  query_family_id
  query_family_version
  source_id
  language
  context_id
  requested_page_limit
  parser_name
  parser_version
  observed_from
  observed_to
  created_at

comparable_set_runs
  set_id
  version
  query_ordinal
  query_text
  probe_run_id

comparable_set_members
  set_id
  version
  ordinal
  platform_listing_id

comparable_set_member_evidence
  set_id
  version
  evidence_ordinal
  platform_listing_id
  probe_run_id
  raw_snapshot_id
  page_index
  source_object_path
```

`yandex_search_union_v1` references exactly one persisted query-family version and exactly one explicit completed `clean_anonymous` search run per family member. All runs share one exact context and requested page limit. The builder replays immutable raw search bodies with `YandexFeedParser@2`, verifies raw request/query/context/pagination metadata plus stored `ProbePage` linkage, excludes sponsored cards, and deduplicates organic results by `yandex_games:<appID>`.

Member `ordinal` is first organic occurrence in deterministic query-family/page/parser-card traversal order. It is provenance/convenience, not a relevance score. `evidence_ordinal` preserves the exact stored evidence tuple order; each evidence row links a member back to its run, raw snapshot, page, and parser-owned source object path.

`observed_from`/`observed_to` declare the actual multi-run observation interval. Identical `(set_id, version)` writes are idempotent; different content is a conflict. Persistence validates the referenced query-family/run/page identities, and reads fail closed if those operational references drift.

The v1 set is a provisional search-derived candidate peer set. It does not auto-filter with the draft taxonomy and does not claim every member is a validated gameplay comparable. Taxonomy-refined construction requires a new explicit method/version later.

General normalized `search_results` persistence remains separate future work; the current v1 comparable construction replays the immutable raw search probe pages directly. `totalGamesCount` remains a per-search supply observation, not competitor count, and must not be summed across query variants as if the result sets were disjoint.

## Collection cadence plans

`collection-cadence-v1` requires a real pre-collection declaration distinct from the later evidence bindings. The operational plan tables are:

```text
collection_cadence_plans
  plan_id
  spec_version
  frozen_at
  content_hash
  query_family_id
  query_family_version

collection_cadence_plan_listings
  plan_id
  ordinal
  listing_id

collection_cadence_plan_checkpoints
  plan_id
  ordinal
  checkpoint_at
```

`plan_id` identifies one immutable declaration. The ordered listing cohort, exact query-family version, and ordered checkpoint schedule determine the plan content hash. Repeating identical content is idempotent; conflicting content under an existing `plan_id` is rejected.

`frozen_at` is generated from the SQLite UTC clock when the plan is first inserted. It is not supplied by the later evidence manifest. The plan must be created before the protocol deadline, and all listing/query-family references must already exist. Reads validate contiguous ordinals and recompute the content hash before returning a stored plan.

The later `CollectionCadenceManifest` stores no independent cohort/freeze declaration. It references `plan_id` and supplies actual feed/search run bindings for the already-frozen checkpoint timestamps. The analyzer requires the evidence schedule to equal the stored plan schedule exactly.

This separation prevents future run IDs from being fictional pre-collection inputs while still making cohort/window predeclaration auditable.

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

A schema fingerprint alone is insufficient. Phase 2 persists replayable structural analyses rather than overwriting one current schema state.

```text
schema_observations
  id
  raw_snapshot_id
  analyzer_version
  contract_id
  comparison_scope_id
  source_id
  request_key
  retrieved_at
  content_hash
  schema_hash
  profile_status
  root_type
  error

schema_field_profiles
  schema_observation_id
  field_path
  value_types
  present_count
  parent_count
  presence_ratio

schema_drift_events
  id
  schema_observation_id
  raw_snapshot_id
  kind
  severity
  field_path
  previous/current types
  previous/current presence ratios
  details
  message
```

`content_hash` binds an analysis to the exact immutable raw body. The same raw snapshot can have multiple analyses when the analyzer or explicit contract changes; historical analyses are not rewritten.

Temporal change detection is scoped by `comparison_scope_id`. A source adapter owns the definition of comparable request context. For Yandex this prevents different devices, search queries, unrelated `get_games` cohorts, first-vs-paginated feed observations, and different persistent session instances from becoming false baselines for one another. Volatile pagination token values, cookie-state fingerprints, and profile age are not themselves part of the comparison identity; a stable persistent `session_instance_id` remains a boundary.

A temporal baseline must be strictly earlier by `retrieved_at`. Equal timestamps are not given a synthetic causal order by snapshot ID, and an out-of-order historical backfill never compares against a future observation.

Current structural checks include:

```text
field presence / new / removed fields
exact JSON value types
important contract fields/types
missingness changes with minimum sample guard
root type
raw JSON parse failures
source-parser failures
```

Breaking explicit-contract drift blocks semantic interpretation only **after** the raw response has been preserved. Warning/info drift remains observable without stopping collection. The registry never silently coerces or auto-adapts parser semantics.

The generic structural profiler currently applies to Yandex JSON `feed`, `search`, and `get_games` responses. Raw `game.page` is HTML; its current drift coverage is parser-failure monitoring around `__playPageData__`, not generic JSON profiling over the HTML document.
