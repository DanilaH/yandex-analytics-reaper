# Analyst Workflow

This document is the operator-facing path for building reproducible current-market inputs from already implemented Yandex evidence primitives.

It is **not** a claim that `START ANALYSIS` has been reached yet. The current commands cover query-family persistence, provisional search-derived comparable-set construction, and immutable analyst-snapshot binding. Analyst-readable export/feature work and the real pilot still remain in `ROADMAP.md`.

## CLI split

```text
yandex-reaper
→ network collection / raw-first probes

yandex-reaper-analyst
→ offline operator workflow over persisted evidence

yandex-reaper-taxonomy
→ offline taxonomy validation artifacts
```

Keep all commands for one local evidence workspace on the same raw root, for example `data/raw`. The operational database then lives at `data/market.sqlite3`.

## 1. Declare a query family

Create a JSON file such as `merge-family.json`:

```json
{
  "family_id": "merge-games",
  "version": 1,
  "label": "merge games",
  "source_id": "yandex_public",
  "language": "ru",
  "created_at": "2026-08-29T17:00:00Z",
  "members": [
    {
      "query_text": "merge",
      "kind": "seed"
    },
    {
      "query_text": "слияние",
      "kind": "synonym"
    }
  ]
}
```

The first member must be the only `seed`. Exact query strings are immutable inside one `(family_id, version)`.

Persist it:

```bash
yandex-reaper-analyst persist-query-family \
  merge-family.json \
  --output data/raw
```

Repeating the exact same declaration is idempotent. Different content under the same family/version is rejected.

## 2. Collect one search run per exact member

Use the same explicit search context and requested page limit for every member. Until collection calibration is complete, these parameters are explicit provisional operating choices rather than empirically optimal defaults.

Example:

```bash
yandex-reaper probe-search "merge" \
  --pages 3 \
  --session-profile clean_anonymous \
  --lang ru \
  --device desktop \
  --platform desktop_other \
  --output data/raw

yandex-reaper probe-search "слияние" \
  --pages 3 \
  --session-profile clean_anonymous \
  --lang ru \
  --device desktop \
  --platform desktop_other \
  --output data/raw
```

Record each returned `run_id`. `yandex_search_union_v1` requires exactly one completed run for every query-family member. It fails closed on missing runs, undeclared query text, mixed contexts, mixed page limits, persistent sessions, or inconsistent raw replay.

## 3. Declare the comparable-set build

Create `merge-comparable.json`:

```json
{
  "construction_method": "yandex_search_union_v1",
  "set_id": "merge-games-search",
  "version": 1,
  "query_family_id": "merge-games",
  "query_family_version": 1,
  "created_at": "2026-08-29T17:30:00Z",
  "run_ids": [
    "probe:<merge-run-id>",
    "probe:<slianie-run-id>"
  ]
}
```

The construction method is explicit and fail-closed so an archived declaration cannot silently acquire a different future construction policy. `created_at` is explicit so the declaration itself is reproducible. Caller run order does not define traversal order; persisted query-family member order does.

Build, raw-replay, validate, and persist the set:

```bash
yandex-reaper-analyst build-search-comparable-set \
  merge-comparable.json \
  --output data/raw
```

The output is the persisted `ComparableSetVersion`, including exact query-family identity, run bindings, context, parser version, observation interval, deduplicated organic members, and raw membership evidence.

## 4. Collect rich metadata for the peer set

Use `probe-games` for the listing IDs you want to enrich. `probe-page` may be added for listings whose page-level metadata is useful.

```bash
yandex-reaper probe-games 123 456 789 --output data/raw
yandex-reaper probe-page 123 --output data/raw
```

Record the returned raw snapshot IDs. Full peer coverage is useful but is not required to create a snapshot: later analytical exports must expose actual metadata coverage/missingness instead of treating missing listings as zeros.

Feed evidence is optional for a snapshot. If a particular analysis uses current feed exposure, collect one or more explicit feed runs under the same effective context as the comparable-set search runs and record their run IDs.

## 5. Freeze an analyst snapshot

Create `analyst-snapshot.json`:

```json
{
  "spec_version": "analyst-snapshot-v1",
  "snapshot_id": "pilot:merge-vs-obby:v1",
  "created_at": "2026-08-29T18:00:00Z",
  "collection_parameters_status": "provisional_uncalibrated",
  "comparable_sets": [
    {
      "set_id": "merge-games-search",
      "version": 1
    },
    {
      "set_id": "obby-games-search",
      "version": 1
    }
  ],
  "feed_run_ids": [
    "probe:<feed-run-id>"
  ],
  "rich_metadata_snapshots": [
    {
      "source_id": "yandex_public",
      "raw_snapshot_id": "<get-games-raw-snapshot-id>",
      "request_key": "catalogue.get_games"
    },
    {
      "source_id": "yandex_public",
      "raw_snapshot_id": "<game-page-raw-snapshot-id>",
      "request_key": "game.page"
    }
  ]
}
```

`collection_parameters_status` is intentionally fixed to `provisional_uncalibrated` in v1. The snapshot records the exact effective context, search depth, and feed depths actually used; it does not call those choices empirically optimal while the calibration track is still unfinished.

Build the create-only report:

```bash
yandex-reaper-analyst build-snapshot \
  analyst-snapshot.json \
  --report data/analysis/pilot-merge-vs-obby-v1.json \
  --output data/raw
```

The builder fails closed unless:

```text
all comparable sets exist and reproduce exactly from their raw search evidence
all comparable sets share one effective context and one requested search depth
all declared feed runs are completed, non-empty, raw-replayable, and use that same context
all rich-metadata snapshots exist, are successful, pass content-hash replay and parser validation
all rich-metadata snapshots contain at least one listing from the declared comparable sets
snapshot created_at is not earlier than any evidence it binds
```

The report stores the effective `ProbeContext`, explicit search/feed page limits, exact comparable/query-family/run bindings, exact rich raw snapshot identities/content hashes, parser versions, relevant listing IDs, and a deterministic report content hash.

The report does **not** require 100% rich-metadata coverage. That is deliberate: coverage is analytical evidence and must be reported by the export/feature layer rather than silently repaired or used as a reason to discard an otherwise reproducible market snapshot.

## Interpretation boundary

`yandex_search_union_v1` is a **provisional search-derived candidate peer set**. It is suitable as an explicit current-market analysis input, but it does not prove that every member is a gameplay comparable and it is not an exhaustive competitor census.

Do not:

```text
sum totalGamesCount across query variants and call it competitor count
count sponsored cards as organic peer evidence
call the current search depth/session choice empirically optimal
call draft taxonomy output validated
infer unavailable competitor DAU, retention, playtime, CTR, revenue, or ARPDAU
```

The next M1 work reads a frozen analyst snapshot into analyst-readable market exports and transparent comparable-market features.
