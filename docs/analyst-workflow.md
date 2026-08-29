# Analyst Workflow

This document is the operator-facing path for building reproducible current-market inputs from already implemented Yandex evidence primitives.

It is **not** a claim that `START ANALYSIS` has been reached yet. The current commands cover query-family persistence and provisional search-derived comparable-set construction. Analyst snapshot/export/feature work still remains in `ROADMAP.md`.

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

The next M1 work binds these collection/comparable artifacts into one analyst snapshot and exposes analyst-readable market exports/features.
