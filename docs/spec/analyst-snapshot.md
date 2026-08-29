# Analyst Snapshot

`analyst-snapshot-v1` freezes the exact current-market evidence used by one human analyst session before analyst-readable aggregation or candidate evaluation.

It is an evidence-binding artifact, not a market conclusion and not a claim that collection parameters are empirically optimal.

## Purpose

The snapshot prevents an analysis from becoming an implicit query over whatever happens to be latest in SQLite.

```text
explicit persisted comparable-set versions
+ optional explicit feed ProbeRun IDs
+ explicit rich-metadata raw snapshot IDs
→ fail-closed evidence replay / compatibility checks
→ immutable analyst snapshot report + content hash
```

Downstream exports/features must consume the frozen snapshot rather than silently selecting newer or more convenient evidence.

## Declaration

The v1 declaration contains:

```text
spec_version = analyst-snapshot-v1
snapshot_id
created_at
collection_parameters_status = provisional_uncalibrated
comparable_sets[] = (set_id, version)
feed_run_ids[]
rich_metadata_snapshots[] = (source_id, raw_snapshot_id, request_key)
```

At least one comparable set and one rich-metadata raw snapshot are required. Feed runs are optional because some current-market questions do not consume feed exposure.

`collection_parameters_status` is deliberately fixed to `provisional_uncalibrated` in v1. Feed-depth, session-profile, and cadence calibration remain separate evidence tracks. A snapshot records what parameters were used; it does not convert those choices into an empirical recommendation.

## Comparable-set binding

Every referenced comparable set must already be persisted.

For each set the builder:

1. reloads its exact query-family version;
2. reruns `yandex_search_union_v1` against the exact persisted search ProbeRun IDs;
3. replays immutable raw search bodies/content hashes and source-page linkage through the existing comparable-set builder;
4. requires the rebuilt `ComparableSetVersion` to equal the persisted version exactly.

All comparable sets inside one snapshot must share:

```text
one effective ProbeContext
one context_id
one requested search page limit
```

This makes comparisons between niches explicit rather than mixing desktop/mobile, language, region, session state, or search depth accidentally.

The snapshot stores each set's exact query-family identity, search run IDs, observed interval, construction method, and ordered organic member IDs.

## Feed binding

A declared feed run must be:

```text
source = yandex_public
request_key = catalogue.feed
kind = recommendation_feed
status = completed
pages >= 1
same effective ProbeContext as the comparable sets
```

Every page is replayed from the immutable raw store with content-hash verification, parsed with the current declared Yandex feed parser, reconstructed through `probe_page_from_yandex`, and required to equal the persisted `ProbePage` exactly.

A partial/failed/running feed run cannot enter a snapshot.

Feed requested page limits are recorded per run. V1 does not require feed depth to equal search depth because those are distinct surfaces; it only requires one compatible effective observation context.

## Rich-metadata binding

V1 accepts successful Yandex raw snapshots from:

```text
catalogue.get_games
game.page
```

For every declared raw snapshot the builder:

1. resolves exact immutable raw metadata;
2. rechecks the stored body SHA-256 content identity;
3. requires the declared request key to match raw metadata;
4. requires a successful HTTP status;
5. reparses the body with the corresponding versioned source parser;
6. derives the parsed Yandex listing IDs;
7. requires at least one parsed listing to belong to the union of the declared comparable sets.

The report records the raw content hash, parser name/version, all parsed listing IDs, and the subset relevant to the snapshot.

## Coverage semantics

V1 intentionally does **not** require rich metadata for every comparable-set member.

Partial coverage is valid evidence and must remain measurable:

```text
53 enriched peers / 80 comparable members
≠
80 complete peers
```

Downstream export/feature layers must expose coverage/missingness and must not replace missing observations with zero, false, or inferred values.

A rich-metadata snapshot with zero relevant comparable members is rejected because it cannot be evidence for the declared analyst session.

## Time boundary

`snapshot.created_at` must be greater than or equal to every bound evidence timestamp:

```text
comparable-set observed_to
feed completed_at
rich raw retrieved_at
```

This prevents a declaration from claiming that the final snapshot existed before evidence it contains.

The timestamp is artifact metadata, not proof of pre-registration and not a source observation timestamp.

## Report identity

The report contains:

```text
snapshot identity / created_at
collection_parameters_status
effective ProbeContext
explicit search page limit
comparable-set bindings
feed-run bindings + page/raw IDs + parser version
rich-metadata bindings + raw content hashes + parser versions
content_hash
```

`content_hash` is deterministic SHA-256 over the canonical JSON representation of all report fields except `content_hash` itself.

The hash is an immutable content identity/corruption check, not a cryptographic signature or proof of authorship.

## Non-claims

An `analyst-snapshot-v1` report does not establish that:

```text
search/feed depth is optimal
clean_anonymous is representative of all users
collection cadence is optimal
the search-derived peer set is exhaustive or gameplay-validated
taxonomy is validated
competitor DAU / retention / playtime / CTR / revenue / ARPDAU is known
```

Those claims require their own evidence and remain governed by the corresponding specifications/roadmap tracks.
