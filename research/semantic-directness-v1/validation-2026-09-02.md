# Semantic Directness v1 — Real Thesis Validation

Date: `2026-09-02`

## Question

Can the narrow lexical semantic layer materially reduce the manual review burden created by fuzzy
Yandex Games search without pretending to make the final competitor judgement automatically?

## Frozen source

Validation replays the existing V3 thesis sweep artifact; it does not recollect Yandex.

```text
experiment_id: microgame-thesis-sweep-v3-2026-09-01
workflow_run: 33538639750
artifact_id: 9812724913
snapshot_id: experiment:microgame-thesis-sweep-v3-2026-09-01:20260901T173529Z
source comparable set: microgame-thesis-sweep-v3-2026-09-01--custom-headphones
source listings: 312
rich metadata coverage: 312 / 312 for target listings
```

The target thesis declaration is frozen in
[`custom-headphones-thesis-v1.json`](custom-headphones-thesis-v1.json).

## Replayed evidence

The validation used only semantic fields already present in frozen `catalogue.get_games` evidence:

```text
title
description
instruction
seoDescription
categoriesNames
```

`categoryIDs` and `tagIDs` are retained in the semantic corpus/provenance artifact but are not used
as lexical match text in v1.

## First-pass result

Using the exact v1 candidate semantics:

| Bucket | Listings | Share of 312 | Meaning |
| --- | ---: | ---: | --- |
| `noise_candidate` | 243 | 77.9% | no declared headphones theme or customization mechanic evidence |
| `adjacent_candidate` | 67 | 21.5% | only one thesis dimension matched |
| `direct_candidate` | 2 | 0.6% | both theme and mechanic terms matched; requires manual confirmation |
| `insufficient_evidence` | 0 | 0.0% | no target listing lacked frozen searchable rich metadata |

The automatic layer therefore reduced the high-priority direct review tail from **312 listings to 2
candidate listings**. This is a triage reduction, not a claim that 310 listings are mathematically
irrelevant to every possible research question.

## Manual review of the two direct candidates

### `yandex_games:289855` — `А4 Аквапринт мастерская челлендж`

Why lexical v1 surfaced it:

- theme evidence: headphones are explicitly listed;
- mechanic evidence: painting/coloring/customization language is present.

Manual judgement:

**not a meaningful direct `custom headphones` competitor.**

The game applies an aqua-print/customization mechanic to many unrelated object types. Headphones are
one object in a broad list alongside gamepads, phones, tablets, hoverboards, drones, clothing,
shoes and accessories. This is useful adjacent grammar evidence, not theme-specific direct supply.

### `yandex_games:517500` — `Лайк Шопинг Модный Лук: Секретный Уровень`

Why lexical v1 surfaced it:

- theme evidence: the cat character is described as wearing headphones;
- mechanic evidence: the player can decorate the room.

Manual judgement:

**not a meaningful direct `custom headphones` competitor.**

The customization verb and the headphones noun refer to different parts of the game. This is the
canonical false-positive shape that a transparent lexical prefilter should expose for quick human
rejection instead of trying to hide behind an opaque score.

## Final thesis-level interpretation

After the two candidate rows are manually inspected:

```text
meaningful direct custom-headphones matches in researched V3 surface: 0
```

This wording remains intentionally bounded. Top-N Yandex search cannot prove absolute market
absence.

The validation supports the intended use of `analyst-semantic-enrichment-v1`:

```text
fuzzy search union
-> cheap reproducible semantic triage
-> tiny candidate tail with evidence snippets
-> manual confirmation/rejection
-> wider market decision
```

It does **not** support replacing the manual confirmation layer with lexical directness.

## What this changes operationally

Before M1.7, a thesis like `custom-headphones` could require manual inspection across hundreds of
fuzzy results or ad-hoc one-off filtering outside the reproducible analyst artifacts.

After M1.7:

- the exact thesis vocabulary is versioned;
- rich text is replayed from frozen raw evidence;
- every positive match carries its evidence term/field/snippet and raw provenance;
- `theme_match` and `mechanic_match` can be inspected independently;
- the highest-priority review queue is reduced to a very small tail;
- final gameplay comparability remains an explicit analyst judgement.

## Known limitations retained on purpose

- substring lexical rules can create false positives;
- vocabulary outside the declared RU/EN terms can create false negatives;
- co-occurrence does not prove that theme and mechanic are causally related in gameplay;
- screenshots/visual framing are still outside Reaper v1 semantic understanding;
- external provenance/trend checks remain separate layers;
- candidate counts are not demand, traffic, revenue or saturation metrics.

These are acceptable for v1 because the goal is **cheap, auditable triage**, not autonomous market
classification.

## Validation decision

**PASS for M1.7 scope.**

The real V3 replay demonstrates a material reduction in fuzzy-search review burden while preserving
manual judgement and evidence provenance. No broader taxonomy system, embeddings, LLM classifier or
new Yandex collection endpoint is justified by this bottleneck.
