# Search Query-Family Model

A search query family is a **versioned, immutable declaration of the exact search texts** used to probe one search intent on one source/language surface.

It exists to make later search-result unions and comparable-set construction reproducible. It is not itself a comparable set, taxonomy classifier, synonym generator, or claim that every member is semantically equivalent in all contexts.

## Boundary

The Phase 2 flow is deliberately staged:

```text
QueryFamilyVersion
→ exact ordered query members
→ search ProbeRuns
→ result union/dedupe
→ taxonomy/similarity filtering
→ versioned ComparableSet
```

This roadmap task owns only `QueryFamilyVersion` and its immutable persistence. Search-result union and comparable-set membership belong to the following roadmap task.

## Versioned identity

A query-family version contains:

```text
family_id
version
label
source_id
language
created_at
members[]
```

Semantics:

- `family_id` is the stable internal family identity across revisions;
- `version` is a positive integer and identifies one immutable declaration;
- `label` is human-readable context, not analytical identity by itself;
- `source_id` is explicit because search behavior/query syntax is source-dependent;
- `language` is explicit because query meaning/coverage is language-dependent;
- `created_at` is timezone-aware provenance for when this declaration was frozen;
- `members` is an ordered non-empty tuple of exact outgoing query texts.

Changing source, language, label, member text, member kind, or member order requires a **new version**. A persisted `(family_id, version)` is never rewritten.

Versions do not imply that observed source results are immutable. They freeze the input definition so observations collected under that definition can be reconstructed later.

## Query members

Each member contains:

```text
query_text
kind
```

Controlled v1 kinds:

```text
seed
synonym
spelling_variant
transliteration
other
```

Rules:

- exactly one member is the canonical `seed`;
- the seed is member 0;
- exact `query_text` values are unique within the version;
- query text must be non-blank and already trimmed;
- the model does **not** case-fold, stem, transliterate, collapse internal whitespace, or otherwise silently normalize query text;
- if two intentionally distinct outgoing strings differ only by case/spacing, they remain distinct declarations and must be entered explicitly.

No member is generated automatically by this model. Human/research tooling may propose candidates later, but promotion into a query-family version is an explicit versioned decision.

## Persistence

Operational SQLite stores:

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

The member ordinal is part of the frozen declaration. Storage must round-trip the exact order.

Writing an identical existing version is idempotent. Writing different content under an existing `(family_id, version)` is a conflict and must fail rather than overwrite history.

Multiple versions of one family coexist. Readers can request an exact version or the highest persisted version; downstream analytical artifacts must store the exact version they consumed rather than relying on `latest` after the fact.

## Relationship to search ProbeRuns

Existing search `ProbeRun` records keep the exact `query_text` that was actually requested. This task does not retroactively attach a family/version foreign key to every manual search run.

A later query-family execution/result-union layer must validate that each run's persisted `query_text` exactly matches a declared member of the chosen `QueryFamilyVersion`, and must record the exact family/version consumed. It must not infer family membership from fuzzy text similarity.

## Relationship to `totalGamesCount`

`totalGamesCount` remains a per-search supply signal. A query family does not turn counts from several variants into a competitor count by summing them. Result-union/deduplication semantics are a separate step.

## Non-goals

This model does not:

- choose query families automatically;
- fetch search results;
- decide search depth;
- merge/dedupe result listings;
- classify taxonomy;
- construct comparable sets;
- assign weights to query variants;
- claim statistical completeness of the declared variants.
