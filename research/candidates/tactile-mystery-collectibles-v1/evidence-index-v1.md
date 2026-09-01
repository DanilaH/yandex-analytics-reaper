# Evidence index v1 — tactile-mystery-collectibles-v1

Purpose: make dossier reconstruction possible from committed evidence without guessing which sweep
artifact supports a claim.

Source root:
[`../../mystery-unboxing-collection-sweep-v1/`](../../mystery-unboxing-collection-sweep-v1/)

## Run identity and completeness

Claim:

```text
experiment mystery-unboxing-collection-sweep-v1
run 20260901T062453Z
36 exact queries
665 unique listings
665 / 665 rich metadata
resume with workers=4
4 reused + 32 collected
verifier PASS
```

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/run-summary.json`
- immutable acceptance/artifact hashes in the same file and
  `../../mystery-unboxing-collection-sweep-v1/EVIDENCE_CHECKSUMS.md`

## Primary structural reference — listing 533677

Claims used in dossier:

```text
title: Сквиш Мистери Дамплинги: Открой Пельмень
age_days: 71.8
ratingCount: 867
player_rating: 4.2
ratingCount / age-days proxy: 12.07
fresh proxy percentile: 65.9
query_hits: 9
family_hits: 6
best observed rank: 2
production burden: very low
reward strength: high
rethemeability: high
```

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
  - key: `listing_id=533677`
- full normalized listing record:
  `../../mystery-unboxing-collection-sweep-v1/listings.csv.gz`
  - key: `platform_listing_id=533677`
- exact family/query membership provenance:
  `../../mystery-unboxing-collection-sweep-v1/comparable_memberships.csv.gz`
  - key: `platform_listing_id=533677`

Interpretation/decomposition is analyst-authored and intentionally lives in
`../../mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`.

## Case-opening reward-grammar benchmark

Claims:

```text
member_count: 48
query supply: 315–316
ratingCount median: 6,609
ratingCount p75: 22,454.75
all-query Jaccard: 0.5
```

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/family-summary.csv`
  - key: `family_id=case-opening`
- `../../mystery-unboxing-collection-sweep-v1/family-coherence.json`
  - key: `family_id=case-opening`
- `../../mystery-unboxing-collection-sweep-v1/search_supply.csv`
  - key: `set_id=mystery-unboxing-collection-sweep-v1--case-opening`

Fresh benchmark listing `540678`:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
  - key: `listing_id=540678`
- full normalized listing + membership provenance in the two gzip files above.

## Simple-opener negative controls

Claims about weak/zero current rating-count traction are bound to:

- `listing_id=524641`
- `listing_id=533962`
- `listing_id=550641`
- `listing_id=545228`

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
- `../../mystery-unboxing-collection-sweep-v1/listings.csv.gz`

The same analyst decomposition explains why these are treated as reskin/mechanic counter-evidence
rather than as a clean market average.

## Generic real-object case negative controls

Claims:

- `listing_id=303374`: 829 ratings at ~817 days with materially larger catalog/meta burden.
- `listing_id=241366`: 306 ratings at ~1,134 days with a cleaner generic real-object case loop.

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
- full normalized records in `../../mystery-unboxing-collection-sweep-v1/listings.csv.gz`

## Search-ranking caution

Claim:

```text
listing 550787
query_hits: 14
family_hits: 8
best observed rank: 1
ratingCount: 0
age_days: ~42.3
```

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`
  - key: `listing_id=550787`
- membership provenance in
  `../../mystery-unboxing-collection-sweep-v1/comparable_memberships.csv.gz`

This is why the dossier refuses to interpret search breadth/rank as demand.

## Lucky-block WATCH evidence

Family claims:

```text
member_count: 44
fresh <=30d: 10
all-query Jaccard: 0.6363636364
```

Evidence:

- `../../mystery-unboxing-collection-sweep-v1/family-summary.csv`
  - key: `family_id=lucky-block`
- `../../mystery-unboxing-collection-sweep-v1/family-coherence.json`
  - key: `family_id=lucky-block`

Reviewed fresh examples:

- `listing_id=527357`
- `listing_id=521326`
- `listing_id=529597`

Evidence:
`../../mystery-unboxing-collection-sweep-v1/candidate-review.csv`.

## Production evidence status

The 5–7 focused-person-day range is **not market evidence**. It is a frozen analyst production
estimate produced under [`production-rubric-v1.md`](production-rubric-v1.md) and must later be
compared with actual build effort. No reusable candidate-specific code is assumed.

## Decision reconstruction path

Another analyst should be able to reconstruct the current action in this order:

```text
run-summary.json
-> manifest.json
-> family-summary.csv + family-coherence.json + search_supply.csv
-> candidate-review.csv
-> full listings/memberships when a row needs provenance
-> opportunity-decomposition.md
-> candidate-v1.json
-> production-rubric-v1.md
-> dossier-v1.md
-> decision-v1.json
```

If the decision cannot be reconstructed from that chain, the dossier is incomplete rather than the
missing fact being silently inferred.
