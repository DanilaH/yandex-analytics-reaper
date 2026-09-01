# Candidate dossier v2 — tactile-mystery-collectibles-v1

Status: **pre-build frozen decision snapshot**  
Candidate version: `2`  
Decision validation status: `heuristic`  
Decision: **BUILD — small probe**  
Evidence date: 2026-09-01

v2 supersedes the first M2 draft after direct public-page/visual review of the primary reference.
The important correction is scope reduction: the reference supports a low-input mystery reveal, not
multi-step tactile simulation. See [`visual-reference-review-v1.md`](visual-reference-review-v1.md).

## 1. Candidate

Working original theme: **Pocket Gremlins: Mystery Desk Toys**.

Frozen loop:

```text
choose mystery package
-> one short deterministic pointer/touch package interaction
-> 0.5–1.5 s anticipation/reveal
-> random original collectible + obvious rarity treatment
-> album fill or duplicate -> soft currency
-> repeat
```

The package interaction may look like a pull tab, peel seal, pop lid, or simple staged click/tap.
It must be authored UI motion, not simulated physics.

Exact identity/scope:
[`candidate-v2.json`](candidate-v2.json).

## 2. Evidence binding

Immutable Reaper evidence:

```text
experiment: mystery-unboxing-collection-sweep-v1
run: 20260901T062453Z
workflow: analyst-experiment-v1.2
release: 0.2.0
families: 15
queries: 36
unique comparable listings: 665
rich metadata: 665 / 665
verifier: PASS
```

Research root:
[`../../mystery-unboxing-collection-sweep-v1/`](../../mystery-unboxing-collection-sweep-v1/)

Claim-by-claim reconstruction:
[`evidence-index-v1.md`](evidence-index-v1.md).

Primary structural reference: Yandex Games listing `533677`,
**«Сквиш Мистери Дамплинги: Открой Пельмень»**.

## 3. What the primary reference actually validates

Sweep evidence for listing `533677`:

```text
age at snapshot: ~71.8 days
ratingCount: 867
player rating: 4.2
rough ratingCount / age-days proxy: 12.07
fresh positive-rating proxy percentile: ~65.9
exact-query exposures: 9
analyst families hit: 6
best observed rank: 2
```

Current public-page review separately confirms an extremely simple documented loop:

```text
choose one of four boxes
-> open
-> receive random dumpling
-> rarity / collection
-> repeat
```

Public page checked:
`https://yandex.ru/games/app/skvish-misteri-damplingi-otkroi-pelmen-533677`

The reference therefore supports:

```text
unknown state
+ near-zero input friction
+ anticipation
+ high-contrast rarity reveal
+ collection completion
```

It does **not** validate extra interaction complexity. That distinction is why candidate v2 uses one
short deterministic interaction rather than 2–4 manipulation steps.

## 4. Market prior — `favorable`

Not `strong_favorable`.

### Supporting evidence

1. **Fresh close structural reference.** Listing `533677` combines current traction proxy,
   random rarity and collection with very low gameplay-system burden.
2. **Reward grammar is independently common in stronger case-opening games.** The `case-opening`
   family has 48 observed members, ratingCount median `6,609`, p75 `22,454.75`, and all-query
   Jaccard `0.5`.
3. **Fresh strong case benchmark.** Listing `540678` had 6,572 ratings at ~76.5 days, supporting the
   appeal of anticipation + rarity + ownership even though its IP/meta structure is not copied.
4. **The candidate can test the grammar cheaply.** It deliberately removes marketplace, contracts,
   ranks, minigames, large catalogs, 3D movement, combat and multiplayer.

### Counter-evidence

Simple opener mechanics are **not** sufficient by themselves:

```text
524641 -> 188 ratings at ~116d
533962 -> 58 at ~90d
541827 -> 0 at ~54d
550641 -> 0 at ~34d despite one observed rank-1 query
545228 -> 0 at ~32d
```

Generic non-IP case re-themes are also weak long-run references:

```text
303374 -> 829 ratings at ~817d despite large catalog/meta
241366 -> 306 ratings at ~1,134d
```

And search matching cannot be read as demand:

```text
550787 -> 14 exact-query exposures, 8 families, best rank 1,
           but ratingCount 0 at ~42d
```

Therefore the candidate thesis is **not** “random boxes work”. It is:

> A very cheap original opener may be worth testing when the product effort is concentrated on the
> unknown -> anticipation -> unusually satisfying rarity reveal -> collection transition rather
> than on a large meta game or commodity reskin catalog.

## 5. Evidence coverage — `medium`

Available:

- exact current Yandex query/comparable evidence;
- 665-listing universe with full rich metadata;
- family coherence and query-supply diagnostics;
- fresh positive benchmark and multiple negative controls;
- current public-page inspection of the primary reference;
- frozen candidate-specific production assessment.

Unknown:

- competitor DAU;
- retention and session depth;
- competitor ad impressions/revenue;
- store-card CTR / acquisition mix;
- historical trajectory before the snapshot;
- click appeal of the original **Pocket Gremlins** creative;
- portfolio-calibrated post-launch thresholds.

This is enough for a low-cost heuristic probe, not for a confident revenue forecast.

## 6. Production assessment

Frozen rubric:
[`production-rubric-v1.md`](production-rubric-v1.md).

| Dimension | v2 assessment | Reason |
|---|---|---|
| `dev_complexity` | `s` | one screen, one deterministic package interaction, reveal + local state |
| `asset_burden` | `medium` | 24 original collectibles + 3 package treatments, one shared grammar |
| `content_burden` | `low` | finite catalog, no authored levels |
| `backend_burden` | `none` | local/platform save is sufficient |
| `balancing_burden` | `low` | 3 package tiers, 4 rarities, one currency |
| `liveops_burden` | `low` | no liveops needed for MVP |
| `qa_burden` | `medium` | save, duplicate economy, ad fallback, touch/mouse reveal flow |
| `mobile_adaptation_burden` | `low` | responsive one-screen pointer/touch primitive |
| `ai_assisted_fit` | `strong` | conventional bounded code + consistent variant asset grammar |

Production fit: **`strong`** for the frozen v2 scope.

### Estimated focused person-days

Analyst estimate; not observed production data.

| Work | Low | High |
|---|---:|---:|
| shell/state/save + Yandex/ad hooks | 0.75 | 1.00 |
| one package interaction + anticipation/reveal | 0.75 | 1.25 |
| rarity/album/duplicate-currency logic | 0.75 | 1.00 |
| 24 collectibles + 3 package treatments + cleanup | 1.00 | 1.50 |
| sound/particles/reveal polish | 0.50 | 0.75 |
| desktop/touch QA + rework + release prep | 0.75 | 1.00 |
| **Total** | **4.50** | **6.50** |

No candidate-specific reusable code is assumed. The estimate is inside the portfolio’s preferred
`<=7 focused person-days` envelope with a small but real margin.

### Main risks

1. **Reveal quality rather than code.** If the rarity reveal feels flat, adding systems is not an
   acceptable rescue plan.
2. **Asset consistency.** 24 AI-assisted collectibles must read as one intentional product family.
3. **Original-theme uncertainty.** Pocket Gremlins is production-friendly but unvalidated as a
   thumbnail/theme hook.
4. **Ad/save edge cases.** Rewarded acceleration and duplicate currency must never corrupt progress.
5. **Polish creep.** The single interaction must remain deterministic; physics/complex animation is
   a scope failure.

## 7. Frozen MVP

```text
24 original collectibles
4 rarities
3 package tiers
1 album
1 soft currency
1 short deterministic package interaction
1 rewarded-ad acceleration point
local/platform save
one-screen core loop
```

Non-goals:

```text
>24 collectibles before first release
second currency
shop economy
dailies / quests
season pass
live events
leaderboard requirement
multiplayer
3D world
combat
base builder
character upgrades
marketplace
physics-based tearing/peeling
```

## 8. Creative grammar

Working theme: **Pocket Gremlins: Mystery Desk Toys**.

Why it is a reasonable production theme:

- original rather than named third-party IP;
- sealed blister/foil package maps naturally to one pull/peel/pop visual action;
- tiny desk creatures can share body/material grammar;
- rarity can be encoded cheaply with finish/accessory/silhouette changes;
- engine and collection data remain re-themeable if the mechanic works but the theme does not.

Example rarity treatment:

```text
common    -> base soft-plastic finish + one desk-object trait
rare      -> material variation / stronger silhouette
 epic     -> premium accessory + glow/animated accent
legendary -> distinctive silhouette + unique reveal treatment
```

The creative must not imitate named Labubu, Brawl, Standoff, Poppy Playtime, or meme-IP characters.

## 9. Monetization hypothesis

Keep first-release monetization subordinate to the behavioral experiment.

Allowed:

- ordinary platform interstitial only at a natural boundary where appropriate;
- one optional rewarded-ad acceleration point.

Not allowed:

- ad between every package;
- progression intentionally made unusable without rewarded ads;
- extra currencies/economy added just to create monetization surfaces.

The first question is whether players voluntarily start another package after a reveal.

## 10. Kill / falsification conditions

### Before release

Demote to WATCH/SKIP if:

1. credible implementation plan exceeds 7 focused person-days;
2. 24 consistent original collectibles require substantial bespoke illustration/3D work;
3. package interaction expands into physics/complex animation;
4. reveal + album prototype is not satisfying without a second gameplay system;
5. creative direction needs recognizable third-party IP to become appealing.

### After release

Instrument at minimum:

```text
session_start
package_selected
package_interaction_started
package_interaction_completed
collectible_revealed
rarity_revealed
album_opened
duplicate_converted
next_package_started
rewarded_ad_offer
rewarded_ad_completed
session_end
```

The product thesis is weakened/falsified if, after a sufficient real traffic cohort:

- behavior is predominantly one reveal -> exit rather than repeat opening;
- album/collection progress shows no continuation signal;
- rewarded monetization is required to make base progress feel usable;
- a heavy meta game becomes the proposed fix for weak reveal/repeat behavior;
- meaningful discovery requires unrelated trend/IP keywords.

No absolute retention/revenue target is invented here because the project has no validated portfolio
baseline. Freeze such thresholds before interpreting post-launch data once an appropriate baseline
exists.

## 11. Decision

```text
decision: BUILD
scope: small_probe
market_prior: favorable
production_fit: strong
evidence_coverage: medium
decision_validation_status: heuristic
```

Hard gates:

- production fit not blocking: PASS;
- critical technical/platform blocker: none known;
- evidence coverage medium+: PASS;
- validated hard negative filter: none exists for this structure.

### Why BUILD

The candidate is cheap enough that a real release is a better next uncertainty-reduction mechanism
than more infrastructure. It combines a current close reference, broadly evidenced reward grammar,
original-IP feasibility, a bounded one-screen scope, strong AI-assisted fit and easy re-themeability.

### Why only a small probe

Weak simple opener controls are abundant, the original theme is unvalidated, and competitor
retention/revenue are unknown. The BUILD action means “run the cheapest credible market experiment”,
not “scale this concept”.

## 12. Next action

Produce one production-ready micro-spec for this **v2 scope only**. If that spec still fits the
4.5–6.5 day estimate and all non-goals remain excluded, route the game into implementation. Do not
insert another Reaper infrastructure milestone between this dossier and that decision.
