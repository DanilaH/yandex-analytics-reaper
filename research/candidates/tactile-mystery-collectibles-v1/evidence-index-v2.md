# Evidence index v2 — tactile-mystery-collectibles-v1

Purpose: reconstruct the current **candidate v2 / decision v2** from committed evidence without
relying on memory or the expired full Actions artifact.

Candidate v1 / dossier v1 / decision v1 and `evidence-index-v1.md` remain immutable audit history.
They were superseded after direct public-page review showed that the primary reference supports a
low-input choose/open/reveal loop, not speculative multi-step tactile manipulation.

## Reconstruction order

```text
research/mystery-unboxing-collection-sweep-v1/run-summary.json
-> manifest.json
-> family-summary.csv + family-coherence.json + search_supply.csv
-> candidate-review.csv
-> listings.csv.gz + comparable_memberships.csv.gz where provenance is needed
-> opportunity-decomposition.md
-> visual-reference-review-v1.md
-> candidate-v2.json
-> production-rubric-v1.md
-> dossier-v2.md
-> decision-v2.json
```

## Run identity / completeness

Evidence root: `../../mystery-unboxing-collection-sweep-v1/`.

Authoritative run identity:

```text
experiment_id: mystery-unboxing-collection-sweep-v1
run_id: 20260901T062453Z
workflow: analyst-experiment-v1.2
release: 0.2.0
queries: 36
unique listings: 665
rich metadata: 665 / 665
final mode: resume
workers: 4
reused queries: 4
collected queries: 32
verifier: PASS
```

Files:

- `../../mystery-unboxing-collection-sweep-v1/run-summary.json`
- `../../mystery-unboxing-collection-sweep-v1/EVIDENCE_CHECKSUMS.md`
- `../../mystery-unboxing-collection-sweep-v1/manifest.json`

## Primary structural reference — listing 533677

Claims used by dossier v2:

```text
title: Сквиш Мистери Дамплинги: Открой Пельмень
age_days_at_snapshot: ~71.8
ratingCount: 867
player_rating: 4.2
ratingCount_per_age_day_proxy: 12.07
fresh_proxy_percentile: ~65.9
query_hits: 9
family_hits: 6
best_observed_rank: 2
```

Files / keys:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
  - `listing_id=533677`
- `../../mystery-unboxing-collection-sweep-v1/listings.csv.gz`
  - `platform_listing_id=533677`
- `../../mystery-unboxing-collection-sweep-v1/comparable_memberships.csv.gz`
  - `platform_listing_id=533677`

Analyst decomposition:
`../../mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`.

Current public-page interpretation and scope correction:
`visual-reference-review-v1.md`.

The public-page review supports:

```text
choose one of four boxes
-> open
-> receive random collectible
-> rarity / collection
```

It does **not** support 2–4 manipulation steps as a validated demand driver. That is why v2 uses
one short deterministic pointer/touch interaction.

## Case-opening reward-grammar benchmark

Claims:

```text
family_id: case-opening
member_count: 48
ratingCount median: 6609
ratingCount p75: 22454.75
all-query Jaccard: 0.5
```

Files:

- `../../mystery-unboxing-collection-sweep-v1/family-summary.csv`
  - `family_id=case-opening`
- `../../mystery-unboxing-collection-sweep-v1/family-coherence.json`
  - `family_id=case-opening`
- `../../mystery-unboxing-collection-sweep-v1/search_supply.csv`
  - `set_id=mystery-unboxing-collection-sweep-v1--case-opening`

Fresh stronger benchmark `listing_id=540678` is recorded in `candidate-review.csv`; it is used only
to support the anticipation + rarity + ownership grammar, not as a scope/IP template.

## Negative controls

Simple opener / reskin counter-evidence:

```text
524641
533962
541827
550641
545228
```

Generic real-object case counter-evidence:

```text
303374
241366
```

Search-ranking caution:

```text
listing 550787
query_hits: 14
family_hits: 8
best observed rank: 1
ratingCount: 0
age_days: ~42.3
```

Primary file: `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`.
Full normalized rows and query provenance live in the two gzip evidence tables.

These controls are why the decision remains `market_prior=favorable`, not `strong_favorable`.

## Production assessment provenance

`production-rubric-v1.md` was frozen before assigning the candidate-specific burden labels.

Current v2 estimate:

```text
dev_complexity: s
asset_burden: medium
content_burden: low
backend_burden: none
balancing_burden: low
liveops_burden: low
qa_burden: medium
mobile_adaptation_burden: low
ai_assisted_fit: strong
estimated_mvp_days: 4.5–6.5 focused person-days
```

This is analyst production evidence, not a Yandex market observation. It must later be compared
against actual build effort.

The reduction from the v1 5–7 day estimate comes only from removing speculative multi-step tactile
interaction scope after `visual-reference-review-v1.md`; no reusable candidate-specific code is
assumed.

## Current decision identity

Current files:

- `candidate-v2.json`
- `dossier-v2.md`
- `decision-v2.json`

Current decision:

```text
BUILD — small_probe
market_prior: favorable
production_fit: strong
evidence_coverage: medium
decision_validation_status: heuristic
```

Superseded audit files remain:

- `candidate-v1.json`
- `dossier-v1.md`
- `decision-v1.json`
- `evidence-index-v1.md`

## Reconstruction criterion

A reviewer should be able to move from the run identity to the exact benchmark rows, counter-
evidence, public-page scope correction, frozen production rubric, candidate v2 scope and final
heuristic decision without inventing any missing fact.

If a future claim cannot be traced through this chain, update the evidence index/version rather
than relying on implicit analyst memory.
