# Listing Update, Status, and Media Histories

Phase 2 needs append-only listing histories that preserve what was actually observed without turning source gaps into invented lifecycle events.

This specification covers three separate observation families:

```text
listing update metadata
listing availability/status
listing media-manifest change
```

They share evidence/lineage infrastructure but remain distinct domain observations. Do not collapse them into one nullable generic state row where `null` ambiguously means both "not observed" and "observed missing".

## Source scope

The first implementation uses only Yandex public surfaces already proven by dated live research:

```text
catalogue.get_games
→ appID
→ media
→ public catalogue presence

__playPageData__.gameData
→ appID
→ appVersion
→ publishedTime
→ public game-page presence
```

No new endpoint or scheduler is introduced by this task.

## Update-history semantics

The first normalized update observation stores:

```text
platform_listing_id
observed_at
app_version
source_published_at
```

At least one of `app_version` / `source_published_at` must be observed.

Yandex `publishedTime` is normalized to `source_published_at`, **not** renamed to `updated_at`. The current evidence proves that this source field exists; it does not prove that every change is a release/update event with a particular product meaning.

Repeated observations therefore form an update-metadata history. A changed `app_version` or `source_published_at` may later support an update event, but this task does not invent such an event automatically.

`firstPublished` remains the listing's first-publication metadata and is not rewritten as update history.

Source-derived text is not silently normalized. In particular, `appVersion` is preserved exactly once parsed; leading/trailing whitespace is rejected at the domain boundary rather than trimmed without a declared transformation.

## Status-history semantics

The first source-neutral status values are intentionally conservative:

```text
published
unknown
```

`published` means a current public Yandex source directly returned the listing/game object or public game-page payload.

`unknown` means the current observation did not establish a more specific status. It is not an alias for unpublished/deleted.

Controlled reasons in v1:

```text
observed_in_catalogue_metadata
observed_on_game_page
requested_but_not_returned
```

For `catalogue.get_games`:

- every returned requested `appID` may produce `published / observed_in_catalogue_metadata`;
- a previously known requested `appID` that is absent from the successful response may produce `unknown / requested_but_not_returned`.

A successful request that omitted one ID is evidence of non-return for that request, **not** proof of `temporarily_unavailable`, `unpublished`, or `deleted`. Those statuses remain future values only when a source can distinguish them reliably.

HTTP/source failures are not converted into listing status. The raw failure remains collection evidence; transport failure is not market state.

## Media-history semantics

The current `get_games` source exposes a `media` object, but its nested source schema has not yet been promoted into a stable cross-source media taxonomy.

The first media observation therefore stores only a deterministic opaque manifest fingerprint:

```text
platform_listing_id
observed_at
manifest_hash
```

`manifest_hash` is SHA-256 over canonical JSON of the exact parsed `media` object:

```text
UTF-8
sorted object keys
compact separators
JSON values preserved
```

The raw snapshot and parser-owned source path remain the authority for the actual source manifest. The hash answers "did the observed manifest change?" without leaking the Yandex DTO shape into platform-neutral analytics.

Missing `media` and present-but-empty `media: {}` are different source facts. The parser preserves that distinction:

```text
field absent/non-object → media = null → no media observation
field present as {}     → media = {}   → hash the empty manifest
```

The pre-history `YandexGetGamesParser@3` collapsed those states. This implementation therefore uses the semantic bump `YandexGetGamesParser@4` with explicit regressions. The parser change does not affect the frozen feed/session experiments, which depend on `YandexFeedParser@2`.

## Normalizer boundary

History semantics belong to a dedicated source normalizer rather than changing unrelated metric semantics:

```text
YandexListingHistoryNormalizer@1
```

This avoids bumping `YandexGameNormalizer` merely because new history outputs were added.

The history normalizer produces platform-neutral observations plus field-level lineage:

```text
appVersion
→ listing_update_observations.app_version

publishedTime
→ listing_update_observations.source_published_at

appID / successful source presence
→ listing_status_observations.status

media
→ canonical SHA-256
→ listing_media_observations.manifest_hash
```

For `requested_but_not_returned`, lineage points to the observed `$.games` collection boundary because the evidence is the requested ID's absence from that successful collection.

Every normalized update/status/media item requires at least one `FieldLineage` record. A source-derived history item without raw lineage is invalid rather than merely lower confidence.

## Persistence

All three histories use the existing normalized-observation envelope:

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

Typed tables:

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

Shared listing-history evidence dimensions are persisted separately by observation ID so update/status/media tables do not duplicate the same evidence schema:

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

Field-level source lineage continues to use `observation_lineage`.

One normalized history bundle is persisted transactionally. The typed row, normalized envelope, evidence row, and field lineage either all commit or all roll back. A lineage conflict must not leave a partially persisted update/status/media bundle.

The persistence boundary revalidates the supplied write instead of trusting an already-created Pydantic object. `normalizer_name` / `normalizer_version` must agree with each lineage `transformation_name` / `transformation_version`; inconsistent provenance is rejected.

A platform listing must already exist before a history row can be persisted. This is especially important for `requested_but_not_returned`: only a previously known listing can acquire that conservative unknown-status observation.

## Observation identity and immutability

Observation identity is deterministic from semantic identity/provenance metadata, including:

```text
source_id
observation_type
platform_listing_id
observed_at
available_at
retrieved_at
normalizer name/version
```

The observed value itself is not part of identity. Rewriting the exact same observation is idempotent; a different update/status/media value or evidence envelope under the same deterministic observation identity is a conflict rather than an overwrite.

## Point-in-time reconstruction

History readers return observations ordered by:

```text
observed_at
retrieved_at
observation_id
```

An optional `as_of` bound filters on `observed_at <= as_of`. The latest returned observation is the latest **observed** state for that history family. Absence of a newer row means "not observed more recently", not "unchanged with certainty".

Readers fail closed on inconsistent stored `observation_type`, missing listing-history evidence, or missing field lineage instead of silently hiding an orphan/corrupt history row.

Media history reconstructs the manifest fingerprint, not the nested Yandex media object. Exact media source content is recovered through lineage → immutable raw snapshot when required.

## Non-goals

This task does not:

- schedule repeated collection;
- infer update events solely from timestamps;
- infer deletion/unpublication from one missing result;
- treat HTTP failure as listing status;
- invent a cross-source media asset taxonomy before the source shape is profiled;
- copy opaque Yandex `media` DTO JSON into platform-neutral domain tables;
- choose collection cadence.
