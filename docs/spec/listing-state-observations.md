# Listing State Observations

`listing_state_observations` stores source-observed descriptive state that is needed for an analyst-readable market snapshot but does not belong in a metric or a dedicated lifecycle history.

It is an append-only normalized observation layer. It does **not** overwrite the separate update/status/media histories defined in `listing-histories.md`.

## Purpose

Current Yandex `get_games` and game-page normalization can produce descriptive fields such as:

```text
title
developer_id
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
```

Before this persisted layer, those fields existed only in the in-memory `ListingStateObservation`. Analyst exports must not reparse raw payloads merely to recover them.

The persistence path is therefore:

```text
immutable raw snapshot
→ versioned source parser
→ YandexGameNormalizer
→ ListingStateObservation + FieldLineage
→ normalized_observations
→ listing_state_observations
→ observation_lineage
```

## Observation identity

One persisted listing state is identified from:

```text
source_id
platform_listing_id
observed_at
available_at
retrieved_at
normalizer_name
normalizer_version
```

The observed field values are deliberately excluded from the identity. Replaying the exact same normalized observation is idempotent; different state/evidence under the same identity is a conflict and must not overwrite the original row.

A platform listing identity must already exist before its listing-state observation is written.

## Evidence and time rules

Every write carries a complete `EvidenceEnvelope` and at least one `FieldLineage` row.

Persisted times must be timezone-aware and, when `available_at` is known, satisfy:

```text
observed_at <= available_at <= retrieved_at
```

Without `available_at`:

```text
observed_at <= retrieved_at
```

Metric periods are not accepted on listing-state evidence.

Every Yandex listing state must include lineage for `platform_listing_id`. Other populated source-observed fields receive their own raw source-field mapping where the parser exposes that field.

## Missingness

Nullable fields remain nullable.

```text
null / absent observation
≠ false
≠ zero
≠ empty inferred value
```

Boolean `false` is persisted distinctly from missing. Empty source arrays remain empty tuples when the parser explicitly observed an array; a missing source field remains `null` where the DTO semantics distinguish it.

Downstream analyst exports must expose missingness rather than imputing values.

## Snapshot-scoped reads

`SQLiteListingStateStore.states_for_raw_snapshots(...)` reads only observations whose field lineage references one of the supplied immutable raw snapshot IDs. An optional listing-ID filter further restricts the result.

This boundary exists so an `analyst-snapshot-v1` export can consume the rich metadata explicitly frozen into that snapshot instead of accidentally reading a newer state from SQLite.

`state_history(...)` remains available for ordered historical inspection and supports an `as_of` bound on observed time.

## Relationship to listing histories

Listing state and listing histories answer different questions:

```text
listing_state_observations
→ descriptive source-observed state used by current-market analysis

listing_update_observations
→ source version/published-time history

listing_status_observations
→ directly observed public availability/status history

listing_media_observations
→ media-manifest history
```

Do not infer a new update/status event merely because a later listing-state row is present or absent. Dedicated history semantics remain owned by `listing-histories.md`.

## Versioning

Adding listing-state field lineage changes `YandexGameNormalizer` from v2 to v3. Existing v2 normalized observations remain valid historical evidence; new normalization writes use v3 and do not mutate old rows in place.
