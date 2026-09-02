# Reaper 0.3 P7 real-data validation — 2026-09-02

Status: **PASS / ACCEPTED FOR MERGE**.

This note records the real-data release validation for Reaper `0.3.0 / Thesis Intelligence`.
It is evidence about the tool contract and reviewed Yandex surface, not a profitability or market-size claim.

## 1. V3 frozen replay controls

Source experiment:

- experiment: `microgame-thesis-sweep-v3-2026-09-01`
- source run: `33538639750`
- source Actions artifact: `9812724913`
- source run id inside artifact: `20260901T173529Z`
- source experiment ZIP sha256: `33ba9c30698f60396ac159380b51df2eee711a0d69dd7bf9d83c115d81173516`

0.3 replay:

- workflow run: `33652516534`
- Actions artifact: `9855412961` (`reaper-0.3-p7-v3-replay`)
- reviewed build input hash: `ca607f0107421e609f2f52008cedf17a5d454c452fb98545b4a7adc1a1fa059b`
- reviewed intelligence ZIP sha256: `0e5b1d484d064962a17a4dd5b4b6ca59e4e95e40561360c803ba2d2f9de303f2`
- reviewed artifact manifest sha256: `87fd46b336025e55aba3c643974123fd0777d627e6f68516faa14ab9fad515c0`
- source-bound verifier: `PASS`

Exact suite declaration is preserved at:
`research/reaper-0.3-p7-validation/v3-suite.json`.

### Control results

| Thesis | Raw union | Lexical direct candidates | Reviewed confirmed direct | Reviewed adjacent | Reviewed not direct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Custom Headphones | 312 | 2 | 0 | 1 | 1 |
| Custom Digicam | 245 | 6 | 0 | 0 | 6 |
| Restore Retro Pocket Tech | 359 | 11 | 0 | 1 | 10 |
| **Total controls** | **916** | **19** | **0** | **2** | **17** |

For these three controls the semantic/directness stage reduced the candidate review surface from
916 fuzzy search-union members to 19 lexical direct candidates: about **97.9% review-queue reduction**.

Important bounded conclusions:

- Custom Headphones remains zero-confirmed-direct in the researched V3 surface. One lexical candidate
  was contextual false-positive and one was broader multi-object customization, not a dedicated
  headphone-customization game.
- Custom Digicam had six lexical direct candidates, all rejected after contextual review.
- Restore Retro Pocket Tech had no confirmed direct match. `yandex_games:413168` (`Симулятор ремонта
  телефонов`) is useful adjacent evidence for repair/diagnosis of phones/electronics, but not a direct
  retro-restoration aesthetic match.
- These are bounded surface conclusions. They do not establish absolute absence from Yandex Games.

The replay also demonstrated the honest zero-history state: no prior artifacts were supplied, so
longitudinal coverage stayed `0.0` rather than fabricating a velocity value.

## 2. Focused Satisfying Destruction sweep

Collection:

- suite: `satisfying-destruction-p7-2026-09-02`
- 1 thesis / 27 exact RU+EN queries / 3 pages / 4 workers
- live workflow run: `33652672808`
- live Actions artifact: `9855432025`
- source run id: `20260902T160512Z`
- source experiment ZIP sha256: `a27a3bdedcf5f917aaffd4675683caa04f45b72e9dc752e5fd6a036227b7f444`
- unique raw union: `504`

The first semantic declaration was intentionally rejected as analyst input because generic terms
such as `всё / вещи / thing / everything` produced 226 lexical direct candidates. That was vocabulary
noise, not evidence of 226 direct competitors.

The same frozen source ZIP was rebuilt without recollection using the refined version-2 thesis
preserved at `research/satisfying-destruction-p7-2026-09-02/suite-v2.json`.

Reviewed offline build:

- workflow run: `33653678856`
- Actions artifact: `9855808323`
- refined lexical direct candidates: `6`
- reviewed: `6 / 6`
- confirmed direct: `4`
- adjacent: `1`
- not direct: `1`
- reviewed build input hash: `b9695979095bb22e213fea4a52dfb112ae35a75b4d76e9ccdf12df009627339c`
- reviewed intelligence ZIP sha256: `78cf6e520666350945124deda6e90b6d8182f34967473f4f6413cc7873af20d9`
- reviewed artifact manifest sha256: `3c64ff0f4b3ba6e2d17b30cede82515d85b83910701275538553c5668ebfd1dc`
- source-bound verifier: `PASS`

The refined semantic stage reduced `504 → 6` lexical direct candidates, about **98.8% review-queue
reduction**.

### Reviewed direct set

Confirmed direct:

- `yandex_games:540826` — `Разнеси Всё В Дребезги!`
- `yandex_games:430845`
- `yandex_games:373094` — `Стреляй по бутылкам`
- `yandex_games:476984`

Adjacent:

- `yandex_games:437035` — superhero/ragdoll combat where object destruction is secondary.

Rejected:

- `yandex_games:513912` — 3D physics puzzle where breaking glass cubes is incidental.

The strongest fresh direct listing is `yandex_games:540826`:

- observed rating count: `734`
- listing age at snapshot: about `65.47` days
- lifetime rating-count pace proxy: `11.2113 / day`
- it appeared across 10 of the 27 exact-query families in the frozen sweep surface.

Only **one** reviewed confirmed-direct listing was fresh within 180 days. Therefore the evidence
supports a real, historically established destruction grammar plus one strong fresh breakout; it
does **not** support a claim of a current fresh clone wave.

## 3. Longitudinal release gate

The frozen contract already covered:

- zero-history -> `no_prior_observation`;
- deterministic selection of the latest eligible explicitly bound prior artifact;
- positive observed delta/day;
- negative revision preserved as negative rather than clamped;
- interval-too-short -> no fabricated daily velocity;
- equal-time conflicting priors -> fail closed;
- missing current rating -> never interpreted as zero.

P7 adds an explicit no-change regression: equal prior/current rating counts across a >=1 day interval
must produce `status=observed`, `rating_count_delta=0`, and `observed_rating_delta_per_day=0.0`.

This satisfies the release requirement using explicit frozen-artifact fixtures; no mutable local DB
history and no fabricated 7d/30d/90d velocity are introduced.

## 4. Measurement-honesty review

Manual review of the comparison outputs found no release-blocking semantic overclaim:

- `direct_candidate` remains a lexical review-queue label, never confirmed competitor truth;
- `confirmed_direct` requires a hash-bound analyst review artifact;
- anomaly counts remain candidates under an explicit policy, not success/profitability labels;
- `ratingCount / age` remains a rough traction proxy, not DAU, plays, revenue or ad impressions;
- zero-history remains explicit rather than silently represented as zero growth;
- comparison output emits evidence and diagnostics but no automatic BUILD/WATCH/SKIP winner.

The Destruction v1→v2 refinement is also a useful validation result: semantic vocabulary quality can
materially change candidate counts, so raw lexical counts must never be interpreted as market size.

## 5. Product-decision impact

P7 does not justify reordering the existing production queue by itself.

- Custom Headphones retains its earlier external-trend and low-production rationale while direct
  Yandex supply remains weak in the researched surface.
- Satisfying Destruction is strengthened as a **RESERVE / research challenger** because a cheap core
  grammar is directly observable and one fresh breakout is strong.
- It is not promoted above the approved-next candidate because the fresh direct evidence is still
  concentrated in one breakout rather than a repeated recent winner pattern.

## 6. Mechanical release gates — PASS

- decision-ledger synchronization merged in `DanilaH/decisions` as squash commit
  `f8cddc223fe6789c9d8ae562f1aefd4ba9fb35ac`;
- code-bearing release head `171e73ae7a58d6add0e9b55ee5329a7040ecb012` passed CI run
  `33657052686` / CI #343: Ruff, strict mypy, full pytest and repository coverage gate all PASS;
- the explicit no-change longitudinal regression is included in that passing run;
- package and runtime version are both `0.3.0`;
- `ROADMAP.md` marks R0.3/P7 complete and points to this validation note;
- exact P7 thesis declarations are preserved in the repository;
- no release-blocking measurement-honesty issue remains.

This status change is documentation-only. The final PR head must still pass the same repository CI
before merge; that final CI is the authoritative merge gate.
