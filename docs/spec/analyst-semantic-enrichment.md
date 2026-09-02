# Analyst Semantic Enrichment v1

## Purpose

`analyst-semantic-enrichment-v1` reduces the repeated manual cost created by fuzzy Yandex Games
search results. It replays semantic text that is already present in frozen `catalogue.get_games`
raw snapshots and produces a transparent first-pass triage for one explicit research thesis.

The unit of analysis is a thesis such as:

```text
mechanic × theme/object
customization × headphones
restoration × retro pocket tech
```

This artifact is a **triage aid**, not a market verdict and not a trained semantic classifier.

## Non-goals

v1 does not:

- infer demand, revenue, DAU, retention or profitability;
- treat search rank or `totalGamesCount` as direct competition;
- declare a listing a confirmed gameplay competitor;
- use embeddings, an LLM, external APIs or opaque scores;
- mutate raw snapshots, comparable sets, normalized observations or historical artifacts;
- replace manual inspection of the small `direct_candidate` / `adjacent_candidate` tail;
- redesign the general taxonomy.

## Inputs

The build consumes exactly two versioned inputs:

1. one valid frozen `AnalystSnapshotReport`;
2. one `analyst-semantic-thesis-v1` declaration.

The thesis declaration contains:

```text
thesis_id
version
label
target_set_ids[]  # optional; empty means all comparable sets in the snapshot
theme.terms[]
mechanic.terms[]
reward_grammar.terms[]  # optional
```

Terms are explicit analyst-owned lexical rules. RU/EN synonyms and object/mechanic phrases should
be declared in the thesis rather than hidden in implementation code.

## Frozen source corpus

v1 reads only `catalogue.get_games` bindings already frozen into the snapshot. It replays the exact
raw body through the same `YandexGetGamesParser` version recorded by the snapshot and verifies the
raw content hash before using it.

For each target listing, the latest bound `catalogue.get_games` observation is selected
reproducibly by `(retrieved_at, raw_snapshot_id)`.

The exported semantic corpus is:

```text
title
description
instruction
seo_description
categories_names[]
category_ids[]
tag_ids[]
```

These fields are already collected by the Yandex rich-metadata path. v1 does not add another
network source or endpoint.

## Text normalization

Before lexical matching:

- HTML entities are unescaped;
- HTML tags are removed for matching/snippets;
- whitespace is collapsed;
- matching is Unicode case-insensitive via `casefold()`.

The stored corpus itself remains the parser output; cleaning is used only for matching and evidence
snippets.

## Dimension results

Each configured dimension produces:

```text
status: match | no_match | unknown | not_configured
matched_terms[]
evidence_snippets[]
```

`unknown` means no searchable text was available from a frozen `catalogue.get_games` source for the
listing. `not_configured` is currently used only for an omitted reward-grammar rule.

Every positive match carries at least one evidence snippet with:

```text
field
term
snippet
```

This makes the heuristic auditable instead of producing an unexplained score.

## Directness triage

`lexical-directness-v1` intentionally uses conservative labels:

```text
theme match + mechanic match -> direct_candidate
exactly one matches          -> adjacent_candidate
neither matches              -> noise_candidate
missing searchable evidence  -> insufficient_evidence
```

The word **candidate** is normative. `direct_candidate` is not equivalent to “confirmed direct
competitor”. Descriptions can be misleading, incomplete or use vocabulary outside the declared
rule set. Final directness remains a human/analyst judgement after inspecting the evidence tail.

Reward-grammar matching is exported independently and does not alter v1 directness. This prevents
an optional subjective dimension from silently changing competitor inclusion.

## Provenance

Every listing with semantic source evidence records:

```text
raw_snapshot_id
retrieved_at
source_object_path
parser_name
parser_version
```

The report also binds:

```text
snapshot_id
snapshot_content_hash
thesis declaration + version
classifier_version
content_hash
```

Rebuilding from identical frozen inputs must produce an identical report.

## Outputs

Canonical JSON artifact:

```text
analyst-semantic-enrichment-v1
```

Optional analyst-readable CSV includes:

- identity/canonical URL;
- comparable-set memberships;
- directness;
- dimension statuses and matched terms;
- semantic corpus fields;
- evidence snippets;
- raw snapshot/source object references.

Both outputs are create-only.

## Decision-use rule

Use this artifact to reduce a fuzzy search union into a smaller review queue. A reasonable workflow
is:

```text
search/comparable-set discovery
-> frozen rich metadata
-> semantic enrichment
-> inspect direct_candidate + adjacent_candidate evidence
-> confirm/reject actual gameplay comparability
-> make market decision using the wider evidence stack
```

Do not aggregate `direct_candidate` count into a market-size or demand metric without an explicit,
separately validated methodology.

## Versioning

Bump the thesis version when analyst-owned lexical rules change materially.

Bump `classifier_version` when directness semantics or matching logic changes.

Create a new artifact spec version if the output contract or provenance semantics change. Never
rewrite historical enrichment artifacts under new rules.
