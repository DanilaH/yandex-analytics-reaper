# Real Analyst Pilot — 2026-08-30

This record closes the real-data execution requirement for **M1.4 — Real analyst pilot** and documents the evidence used to verify the `START ANALYSIS` gate.

Runtime evidence itself remains outside Git. The reviewed archive was:

```text
pilot-v0-artifacts.zip
sha256 = d6952e39578001103e0fa9fb30d7a7b5df4591477f37ad2b62749c2edeb91f94
```

The pilot ran against repository main commit:

```text
dc43cf62f04c09783bae3d3823583d3c28366e26
```

Local runtime reported Python `3.14.3`. The project compatibility target remains Python `>=3.12`; this pilot is runtime evidence for the analyst workflow, not a replacement for the project's Python 3.12 compatibility contract.

## Pilot scope

One explicit provisional collection context was used for all four search runs:

```text
language = ru
device = desktop
platform = desktop_other
session_profile = clean_anonymous
search_page_limit = 3
collection_parameters_status = provisional_uncalibrated
```

Two explicit query families were collected:

```text
merge-games@1
  seed: merge
  synonym: слияние

obby-games@1
  seed: obby
  synonym: обби
```

Selected completed search runs:

```text
merge   probe:b2a0621489b040db856b9deaa58b9719
слияние probe:8bed9051a3c14d58ba4b59d8c6526f65
obby    probe:401e53e457f8400590190429a04922ad
обби    probe:c18602e8e6694c08b399640f464fe789
```

Each selected run completed three pages. Each query exposed 36 unique results. Observed query-level `totalGamesCount` values were:

```text
merge   417
слияние 424
obby    402
обби    404
```

These are preserved as query-supply observations only; they are not treated as canonical competitor counts.

## Comparable sets and enrichment

The explicit `yandex_search_union_v1` comparable sets were:

```text
merge-games-search@1  57 members
obby-games-search@1   38 members
```

The two sets had no overlapping listing IDs in this pilot, for 95 unique comparable listings total.

One `catalogue.get_games` raw snapshot enriched the full 95-listing union:

```text
raw_snapshot_id = 20260830T121237362978Z-0fd4a75803
parsed listings = 95
relevant listings = 95
```

No feed or game-page evidence was collected. Page-only listing fields therefore remain explicitly `not_observed`; feed exposure is represented as unavailable evidence rather than zero exposure.

## Frozen artifact chain

The reviewed artifacts form this exact content-hash chain:

```text
analyst snapshot
4a35158f24407d7eb177b86a44e18f0d43bfd7460b330d6c7a966ff9a2e4d1fe

market export
8b35849d77ea567849fff87d9b26fcf295360f5471539a7acd659a8b998f4d7e

market features
740d4a6625243d905801766bf9e2e1042071f7be2f330a1b79514cedaeb17f30

pilot verification
35fe288a46e82e89c9bf8b076d3e4e66846ccaaccefb13bf323b566b04543bc3
```

The pilot verifier passed and reported:

```text
comparable_set_count = 2
query_family_ids = [merge-games, obby-games]
referenced_raw_snapshot_count = 13
verified_raw_snapshot_count = 13
```

## Independent review performed after the verifier

The supplied runtime archive was independently inspected rather than accepting the verifier summary alone.

The review confirmed:

1. The archive contains exactly 13 raw `body.json` / `metadata.json` pairs referenced by the pilot verifier: 12 search pages plus one `get_games` response.
2. SHA-256 was recomputed directly over every raw body. All 13 bodies match their persisted `metadata.content_hash`.
3. The four selected comparable-set run IDs are `completed`, share the same explicit context, and each contain exactly three persisted pages.
4. One earlier `obby` transport attempt is persisted as a terminal `failed` run with no page evidence and is not referenced by either comparable set.
5. The SQLite database is schema version 12 and contains exactly the two expected query-family versions and comparable-set versions.
6. Comparable-set persistence contains 57 and 38 members respectively, with 72 source exposure evidence rows per set.
7. The 95 IDs returned by the rich `get_games` raw response exactly equal the 95-listing union of both comparable sets; there are no extra or missing enriched listings.
8. Metric observations use `YandexGameNormalizer@2`; listing-state observations use `YandexGameNormalizer@4`, preserving the intended split between frozen metric semantics and newer listing-state lineage semantics.
9. Representative `rating_count` traces were replayed directly against raw JSON source paths for every contribution in both sets. Listing ID, raw source value, source field path, and reported median all matched.
10. The four top-level artifact `content_hash` values were independently recomputed from canonical compact sorted-key JSON payloads and all matched.
11. All six current-state distribution summaries (`rating_count`, Yandex Games rating, player rating across both comparable sets) were independently recomputed from listing-level export values, including median, mean, p25, p75, minimum, maximum, and coverage; all matched `market-features.json`.
12. First-published age distributions/windows, developer concentration, and search exposure summaries were independently recomputed and matched the feature report.
13. Analyst CSV exports are usable without direct SQLite access: 95 listing rows, 95 comparable-membership rows, 144 search-exposure rows, and 12 query-supply rows expose current values, source queries, run/raw provenance, and missing-field markers.

## Real limitations exposed by the pilot

The machine-detected limitations remain valid:

- collection parameters are still `provisional_uncalibrated` pending calibration tracks;
- search-derived comparable sets are provisional candidate peer sets pending taxonomy validation/refinement;
- feed evidence was intentionally not collected;
- `obby-games-search@1` has one missing Yandex Games (`gqRating`) value among 38 members.

The real run also exposed two operational/analytical limitations that synthetic fixtures did not demonstrate:

### Transient transport failure

The first `obby` attempt failed during the TLS handshake:

```text
ConnectTimeout: _ssl.c:1063: The handshake operation timed out
```

The failed run remains persisted in SQLite and is not referenced by the selected comparable set. Re-running the exact query/context/depth produced a clean completed run. This is acceptable for the current manual analyst workflow and does not justify pulling scheduled retry/orchestration work forward from the later operational-automation milestone.

### Query-family coherence varies materially

The two query variants inside each family did not behave equally:

```text
merge / слияние
  36 results each
  intersection = 15
  union = 57
  Jaccard = 15 / 57 ≈ 0.263

obby / обби
  36 results each
  intersection = 34
  union = 38
  Jaccard = 34 / 38 ≈ 0.895
```

This does **not** invalidate the workbench: query-family members, source queries, exposure rows, and comparable membership remain explicit and inspectable. It does show that an analyst must review query-family construction rather than assuming that a seed and a nominal synonym form an equally coherent market slice. Until taxonomy/refined comparable construction is validated, search-derived sets remain explicitly provisional.

This limitation is not promoted into a hidden automatic threshold. It is an analyst judgment signal discovered by the first real use.

## Practical-analysis verdict

The real workflow satisfied the `START ANALYSIS` requirements:

```text
real Yandex evidence
→ explicit query family / market question
→ reproducible comparable set
→ current supply / quality / traction-proxy evidence
→ comparison of multiple niches
→ visible missingness and provenance
```

The pilot demonstrates that a human analyst can work from supported CLI-generated JSON/CSV artifacts without ad-hoc SQLite queries, while retaining traceability to exact normalized observations and immutable raw evidence.

No blocker requiring additional M1 implementation was found. The remaining calibration, taxonomy validation, feed enrichment, retry automation, historical backtesting, and dashboard/automation work stay in their existing later/parallel roadmap tracks.

**Result: M1.4 passed. `START ANALYSIS` is satisfied.**
