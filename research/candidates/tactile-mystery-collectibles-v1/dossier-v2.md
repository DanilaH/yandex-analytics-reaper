# Candidate dossier v2 — tactile-mystery-collectibles-v1

Status: **pre-build frozen decision snapshot**  
Candidate version: `2`  
Decision validation: `heuristic`  
Decision: **BUILD — small probe**  
Evidence date: 2026-09-01

v2 supersedes the first M2 draft after direct public-page review of the primary reference. The
scope correction is intentional: the observed reference supports a low-input mystery reveal, not a
multi-step tactile simulation.

## 1. Candidate thesis

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

The interaction may visually resemble a pull tab, peel seal, pop lid or staged click/tap. It must
be authored UI motion rather than simulated physics.

Exact scope: [`candidate-v2.json`](candidate-v2.json).

## 2. Evidence binding

Immutable market evidence:

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
[`../../mystery-unboxing-collection-sweep-v1/`](../../mystery-unboxing-collection-sweep-v1/).

Claim-by-claim reconstruction:
[`evidence-index-v2.md`](evidence-index-v2.md).

Primary structural reference: Yandex Games listing `533677`,
**«Сквиш Мистери Дамплинги: Открой Пельмень»**.

Direct public-page interpretation:
[`visual-reference-review-v1.md`](visual-reference-review-v1.md).

## 3. Primary reference signal

Snapshot evidence for `533677`:

```text
age: ~71.8 days
ratingCount: 867
player rating: 4.2
ratingCount / age-days proxy: 12.07
fresh positive-rating proxy percentile: ~65.9
exact-query exposures: 9
analyst families hit: 6
best observed rank: 2
```

The current public page documents a simple structure:

```text
choose one of four boxes
-> open
-> receive random dumpling
-> rarity / collection
-> repeat
```

It supports:

```text
unknown state
+ near-zero input friction
+ anticipation
+ high-contrast rarity reveal
+ collection completion
```

It does **not** validate extra manipulation complexity. Candidate v2 therefore uses one short
interaction, not the speculative 2–4 action sequence from v1.

## 4. Market prior — `favorable`

Not `strong_favorable`.

Supporting evidence:

1. Listing `533677` is a fresh close structural reference with non-zero traction proxy and very low
   gameplay-system burden.
2. `case-opening` independently supports the broader anticipation + rarity + ownership grammar:
   48 observed members, ratingCount median `6,609`, p75 `22,454.75`, all-query Jaccard `0.5`.
3. Fresh benchmark `540678` reached 6,572 ratings at ~76.5 days, showing that this reward grammar can
   accumulate strong current traction when paired with a stronger meta/IP package.
4. This candidate tests only the cheap grammar: no marketplace, contracts, rank system, minigames,
   3D movement, combat or multiplayer.

Counter-evidence is substantial:

```text
524641 -> 188 ratings at ~116d
533962 -> 58 at ~90d
541827 -> 0 at ~54d
550641 -> 0 at ~34d
545228 -> 0 at ~32d
```

Generic non-IP case re-themes are also weak long-run references:

```text
303374 -> 829 ratings at ~817d
241366 -> 306 ratings at ~1,134d
```

Search breadth is not demand:

```text
550787 -> 14 exact-query exposures
           8 families
           best rank 1
           ratingCount 0 at ~42d
```

Therefore the thesis is **not** “random boxes work”. It is:

> A very cheap original opener is worth a real probe when effort is concentrated on the
> unknown -> anticipation -> satisfying rarity reveal -> collection transition rather than on a
> large meta game or commodity reskin catalog.

## 5. Evidence coverage — `medium`

Available:

- exact current Yandex query/comparable evidence;
- 665 enriched unique listings;
- query supply and family coherence;
- fresh positive benchmark plus multiple negative controls;
- current public-page inspection of the primary reference;
- frozen candidate-specific production rubric and assessment.

Unknown:

- competitor DAU and retention;
- competitor revenue/ad efficiency;
- store-card CTR and acquisition mix;
- historical pre-snapshot trajectory;
- click appeal of the original Pocket Gremlins theme;
- portfolio-calibrated success thresholds.

This is enough for a low-cost heuristic probe, not a revenue forecast.

## 6. Production assessment

Frozen rubric: [`production-rubric-v1.md`](production-rubric-v1.md).

| Dimension | v2 |
|---|---|
| `dev_complexity` | `s` |
| `asset_burden` | `medium` |
| `content_burden` | `low` |
| `backend_burden` | `none` |
| `balancing_burden` | `low` |
| `liveops_burden` | `low` |
| `qa_burden` | `medium` |
| `mobile_adaptation_burden` | `low` |
| `ai_assisted_fit` | `strong` |

Production fit: **`strong`** for the frozen v2 scope.

Estimated focused person-days:

| Work | Low | High |
|---|---:|---:|
| shell/state/save + Yandex/ad hooks | 0.75 | 1.00 |
| one package interaction + anticipation/reveal | 0.75 | 1.25 |
| rarity/album/duplicate-currency logic | 0.75 | 1.00 |
| 24 collectibles + 3 package treatments + cleanup | 1.00 | 1.50 |
| sound/particles/reveal polish | 0.50 | 0.75 |
| desktop/touch QA + rework + release prep | 0.75 | 1.00 |
| **Total** | **4.50** | **6.50** |

No candidate-specific reusable code is assumed. The range fits the portfolio `<=7 focused
person-days` preference, but the margin is small enough that scope creep is a kill condition.

Main risks:

1. reveal quality is the product; flat reveal cannot be rescued with more systems;
2. 24 AI-assisted collectibles must read as one intentional family;
3. Pocket Gremlins is production-friendly but not market-validated as a theme;
4. save/rewarded-ad edge cases must not corrupt progress;
5. physics or elaborate animation would invalidate the production estimate.

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

Explicit non-goals:

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

It is useful because it is original, compact, re-themeable and compatible with a shared asset
grammar. The market data validates the reward structure, **not** the specific gremlin theme.

Rarity grammar:

```text
common    -> base material + simple desk-object trait
rare      -> material variation / stronger silhouette
epic      -> premium accessory + glow/animated accent
legendary -> distinctive silhouette + unique reveal treatment
```

Do not imitate named Labubu, Brawl, Standoff, Poppy Playtime or meme-IP characters.

## 9. Monetization hypothesis

Monetization is subordinate to the behavioral test.

Allowed:

- ordinary platform interstitial at a natural boundary when appropriate;
- one optional rewarded-ad acceleration point.

Not allowed:

- ad between every package;
- unusable base progression without rewarded ads;
- extra currencies or systems created merely to add monetization surfaces.

The first product question is whether players voluntarily start another package after a reveal.

## 10. Kill / falsification conditions

Pre-build demotion to WATCH/SKIP if:

1. credible plan exceeds 7 focused person-days;
2. 24 consistent original collectibles require substantial bespoke illustration/3D work;
3. package interaction expands into physics or complex animation tooling;
4. reveal + album prototype is not satisfying without a second gameplay system;
5. creative direction needs recognizable third-party IP to become appealing.

Minimum launch instrumentation:

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

Post-launch thesis weakens/fails if:

- sessions are predominantly one reveal -> exit instead of repeat opening;
- album/collection progress produces no continuation signal;
- rewarded monetization is required for acceptable base progression;
- a heavy meta game becomes the proposed fix for weak reveal/repeat behavior;
- discovery depends on unrelated trend or third-party-IP keywords.

No absolute retention/revenue threshold is invented before a suitable portfolio baseline exists.

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
- validated hard negative filter: none for this structure.

### Why BUILD

A real release is now a cheaper uncertainty-reduction mechanism than further analytical or runner
infrastructure. The candidate combines a current close reference, broadly evidenced reward grammar,
original-IP feasibility, bounded one-screen scope, strong AI-assisted fit and easy re-themeability.

### Why only a small probe

Weak simple opener controls are abundant, the original theme is unvalidated, and competitor
retention/revenue are unknown. BUILD means **run the cheapest credible market experiment**, not
scale the concept.

Machine-readable decision:
[`decision-v2.json`](decision-v2.json).

## 12. Next action

Produce one production-ready micro-spec for this **v2 scope only**. If the implementation plan still
fits 4.5–6.5 focused person-days and all non-goals remain excluded, route it into implementation.
Do not insert another Reaper infrastructure milestone between this dossier and the build test.
