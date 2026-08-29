# Comparable-Set Construction

Phase 2 needs reproducible peer-set inputs before the draft taxonomy has been validated. Therefore the first comparable-set implementation is deliberately a **search-derived provisional candidate set**, not a claim that every member is a true gameplay comparable.

Taxonomy-based refinement belongs to the later taxonomy-validation work. This phase must not silently treat draft classifier output as validated market truth.

## Construction method

The first frozen construction method is:

```text
construction_method = yandex_search_union_v1
parser = YandexFeedParser@2
```

Inputs:

```text
one exact persisted QueryFamilyVersion
+
exactly one completed Yandex search ProbeRun for every query-family member
```

The family/version and all run IDs are explicit inputs. The builder never searches the operational database for convenient runs automatically.

## Eligible search-run cohort

Every submitted run must satisfy:

```text
source_id = query_family.source_id = yandex_public
probe_kind = search
request_key = catalogue.search
status = completed
query_text = exact query-family member text
language = query_family.language
session_profile = clean_anonymous
session_instance_id = null
cookie_state_hash = null
profile_age_days = 0
country_observed = null
collector_region = null
```

All runs in one construction must also share the exact same effective `ProbeContext` and the same `requested_page_limit`.

There must be exactly one run for every query-family member and no run for undeclared query text. Query/run association is derived from persisted exact `query_text`, not caller position and not fuzzy text matching.

Legitimate source exhaustion before the requested page limit remains a completed observation. Different query members may exhaust at different page counts.

The first construction intentionally requires `clean_anonymous` because the session-profile stability experiment is still empirically pending. Do not collapse persistent and clean search observations into one comparable-set cohort before evidence supports that policy.

## Raw replay and membership evidence

Decision-relevant membership must remain traceable to immutable source evidence. For every submitted run the builder:

```text
loads ordered ProbePages
→ loads immutable raw metadata/body
→ verifies content SHA-256
→ requires successful HTTP status
→ validates exact raw query/context/pagination request metadata
→ parses with YandexFeedParser@2
→ reconstructs ProbePage from raw request/context + parsed pagination
→ requires reconstructed ProbePage == stored ProbePage
```

`yandex_search_union_v1` deliberately uses the **parsed-card semantics of `YandexFeedParser@2`**. That parser deduplicates repeated `appID` values within one raw page and retains the first parsed representation. This construction does not reinterpret the same raw page with a second competing parser merely to recover duplicate representations.

Only parsed organic search cards enter `yandex_search_union_v1`. A parsed sponsored card is not search-relevance evidence for peer-set membership. If future evidence shows that parser-level first-representation dedupe materially hides useful organic occurrences, fix that with a new parser/construction version rather than silently changing historical v1 membership.

For every parsed organic occurrence that supports membership store provenance:

```text
query member ordinal
probe_run_id
raw_snapshot_id
page_index
source_object_path
```

The source object path is parser-owned raw lineage such as `$.feed[0].items[3]`. Immutable raw bodies remain available for future re-interpretation under a new explicit parser/construction version.

## Union and deterministic order

The candidate union is deduplicated by stable platform listing ID:

```text
yandex_games:<appID>
```

Traversal order is frozen:

```text
query-family member ordinal
→ page_index
→ parsed organic card order within the page
```

A listing receives its comparable-set `ordinal` at its first parsed organic occurrence in that traversal. Later parsed organic occurrences add evidence but do not create duplicate members or change the first-occurrence ordinal.

This ordering is deterministic provenance/convenience. It is **not** a relevance score or ranking model.

## Comparable-set version

Persist:

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
```

`observed_from` is the earliest submitted run start. `observed_to` is the latest submitted run completion. The set therefore declares its actual observation interval instead of pretending several sequential queries happened at one instant.

Persist exact run membership:

```text
comparable_set_runs
  set_id
  version
  query_ordinal
  query_text
  probe_run_id
```

Persist deduplicated members:

```text
comparable_set_members
  set_id
  version
  ordinal
  platform_listing_id
```

Persist parsed organic membership evidence:

```text
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

`evidence_ordinal` preserves the exact deterministic evidence tuple produced by the frozen traversal. It is a storage-order field, not a relevance/ranking score. Keeping it explicit makes persistence round-trippable and prevents SQLite row order from silently changing the evidence sequence.

The exact same `(set_id, version)` write is idempotent. Different content under an existing identity is a conflict and must never overwrite history. Persistence validates the referenced query family, search runs/context, observation interval, and probe-page raw identities; reads fail closed if those references drift.

## Coverage semantics

A search-derived set represents **the union observed under its exact family, context, page limit, run IDs, parser version, and time interval**. It is not declared exhaustive merely because every query-family member was executed.

`totalGamesCount` remains a per-query supply signal and is not summed into comparable-set size.

## Relationship to taxonomy

`yandex_search_union_v1` is a candidate peer set. Until taxonomy validation is complete:

- do not label every member a confirmed gameplay comparable;
- do not auto-remove members using the draft classifier;
- do not use the set as if taxonomy precision had already been established.

A later construction version may reference a frozen taxonomy/classifier version and persist inclusion/exclusion reasoning. That future refinement must not rewrite historical `yandex_search_union_v1` sets.

## Non-goals

This task does not:

- generate query families;
- choose search depth automatically;
- infer missing query-family members;
- merge different session contexts;
- classify games with the draft taxonomy;
- score/rank peers by quality or opportunity;
- claim the observed search union is the complete competitor market.
