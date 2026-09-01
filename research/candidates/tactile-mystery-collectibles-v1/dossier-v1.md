# Candidate dossier v1 — tactile-mystery-collectibles-v1

Status: **pre-build frozen decision snapshot**  
Decision validation status: `heuristic`  
Decision: **BUILD — small probe**  
Evidence date: 2026-09-01

## 1. Candidate identity

Candidate ID: `tactile-mystery-collectibles-v1`  
Working original theme: **Pocket Gremlins: Mystery Desk Toys**

The theme is a production direction, not a claim that “desk toys” are independently validated by
market evidence. The market thesis is the interaction/reward grammar:

```text
choose mystery package
-> perform 2–4 tactile unwrap actions
-> anticipation beat
-> reveal random collectible + rarity
-> fill album / convert duplicate to soft currency
-> repeat
```

Third-party IP is explicitly out of scope. The build must use original characters/assets.

Exact candidate identity is frozen in [`candidate-v1.json`](candidate-v1.json).

## 2. Evidence binding

This dossier is bound to:

```text
experiment: mystery-unboxing-collection-sweep-v1
run: 20260901T062453Z
workflow: analyst-experiment-v1.2
release: Reaper 0.2.0
families: 15
exact queries: 36
unique listings: 665
rich metadata: 665 / 665
verifier: PASS
```

Permanent source package:
[`../../mystery-unboxing-collection-sweep-v1/`](../../mystery-unboxing-collection-sweep-v1/)

Primary reference listing: Yandex Games `533677`,
**«Сквиш Мистери Дамплинги: Открой Пельмень»**.

## 3. Market prior

Decision dimension: **`favorable`**, not `strong_favorable`.

### Supporting evidence

#### A. A current close structural reference exists

Listing `533677` is unusually close to the desired production shape:

- age at snapshot: ~71.8 days;
- `ratingCount=867`;
- player rating `4.2`;
- rough `ratingCount / age-days` proxy: `12.07`;
- ~65.9th percentile of the sweep’s fresh positive-rating proxy distribution;
- observed in nine exact-query result sets across six analyst families;
- best observed rank: 2;
- four mystery box types;
- random rarity reveal;
- collection as the stated goal;
- no movement/combat loop;
- instruction length: 36 words.

This is promising current evidence for a compact mystery collectible loop. It is **not** breakout
proof and does not reveal DAU, retention or revenue.

#### B. The larger case-opening market validates anticipation + rarity reward

The `case-opening` family has materially stronger current rating-count proxies than generic
unboxing:

```text
observed members: 48
query supply: 315–316
median ratingCount: 6,609
p75 ratingCount: 22,454.75
all-query Jaccard: 0.500
```

A fresh example, listing `540678` («Станд Кейс Симулятор»), had 6,572 ratings at ~76.5 days.
Older case simulators also show large rating-count histories.

This supports the **reward grammar** — anticipation, rarity, inventory/collection — but not a clone
strategy. Strong examples often rely on recognizable IP/theme and deeper meta systems.

#### C. The candidate can borrow the validated reward grammar without inheriting the expensive meta

The candidate intentionally removes:

```text
marketplace
contracts
rank progression
minigames
large item catalogs
3D movement
combat
multiplayer
```

The experiment is whether much better physical/tactile reveal presentation can carry a deliberately
small collection loop.

### Counter-evidence

#### A. Cheap opener/reskin games are mostly weak

Direct negative controls from the same sweep:

- `524641`: 188 ratings at ~116 days;
- `533962`: 58 ratings at ~90 days;
- `541827`: 0 ratings at ~54 days;
- `550641`: 0 ratings at ~34 days despite a best observed rank of 1 for one query;
- `545228`: 0 ratings at ~32 days.

Several use almost the same cheap structure:

```text
open pack
-> receive random character
-> collection / passive currency
-> more packs
```

Therefore **the bare mechanic is not sufficient**. Presentation/theme/reward strength must be the
product, not a commodity asset reskin.

#### B. Generic non-IP case re-themes are weak long-run references

- `303374` («Кейс Симулятор Реальных Вещей»): 829 ratings after ~817 days despite a large item
  catalog, tasks/upgrades and minigames.
- `241366` («Симулятор Кейсов: Реальные Вещи»): 306 ratings after ~1,134 days.

A generic “cases, but with ordinary real objects” re-theme is not the opportunity.

#### C. Search exposure is not demand

Listing `550787` appeared in 14 exact-query exposures across eight analyst families and reached
observed rank 1, yet had `ratingCount=0` at ~42 days.

So this dossier does not treat query breadth or search rank as traffic/product-market-fit evidence.

## 4. Evidence coverage

Decision dimension: **`medium`**.

Present:

- real current Yandex search evidence;
- exact query/run/raw provenance;
- 665-listing comparable universe;
- full rich metadata coverage;
- family coherence diagnostics;
- representative positive and negative controls;
- production decomposition for the selected candidate.

Missing / unknown:

- competitor DAU;
- retention/session depth;
- competitor ad impressions/revenue;
- CTR and store-card impressions;
- acquisition source mix;
- historical trajectory before the snapshot;
- independent validation that the proposed **Pocket Gremlins** theme itself attracts clicks;
- portfolio-calibrated success thresholds for this game type.

The evidence is sufficient for a cheap heuristic BUILD probe, not sufficient for a high-confidence
market forecast.

## 5. Production assessment

Assessment rubric:
[`production-rubric-v1.md`](production-rubric-v1.md)

### Frozen labels

| Dimension | Assessment | Rationale |
|---|---|---|
| `dev_complexity` | `s` | one-screen stateful loop + custom unwrap/reveal; no world/network/backend |
| `asset_burden` | `medium` | 24 original collectibles + package art, but one shared visual grammar |
| `content_burden` | `low` | finite catalog; no authored levels or ongoing content required for MVP |
| `backend_burden` | `none` | local/platform save is sufficient |
| `balancing_burden` | `low` | 3 package tiers, 4 rarities, one currency |
| `liveops_burden` | `low` | no liveops required for MVP |
| `qa_burden` | `medium` | pointer/touch unwrap, persistence, duplicate economy, rewarded-ad fallback |
| `mobile_adaptation_burden` | `low` | one responsive screen and pointer/touch interaction |
| `ai_assisted_fit` | `strong` | bounded conventional code + shared collectible visual grammar |

Production fit: **`acceptable`**.

### Estimated focused person-days

This is an analyst estimate, not observed production data.

| Work | Low | High |
|---|---:|---:|
| shell/state/save + Yandex/ad hooks | 0.75 | 1.00 |
| package selection + tactile unwrap/reveal interaction | 1.00 | 1.50 |
| rarity/collection/duplicate-currency logic | 0.75 | 1.00 |
| 24 collectible assets + 3 package treatments + cleanup | 1.00 | 1.50 |
| sound/particles/reveal polish | 0.50 | 0.75 |
| desktop/touch QA, rework, release preparation | 1.00 | 1.25 |
| **Total** | **5.00** | **7.00** |

The candidate only passes the portfolio constraint while the frozen MVP scope is defended.

### Major production risks

1. **Tactile interaction scope creep.** Realistic tearing/peeling can become animation/physics work.
   Mitigation: use deterministic staged pointer gestures and authored transitions, not simulation.
2. **Reveal quality.** The core must feel materially better than the weak commodity opener controls.
   This may consume polish time faster than code time.
3. **Asset consistency.** AI-assisted generation is useful only if the 24 collectibles look like one
   intentional product family; a style bible and shared silhouette/material rules are required.
4. **Theme risk.** “Pocket Gremlins / desk toys” is original and production-friendly but not directly
   validated by the market sweep.
5. **Save/ad edge cases.** Duplicate conversion and rewarded acceleration must fail safely without
   corrupting the small economy.

No candidate-specific reusable code is assumed in the estimate. Standard web/pointer/Yandex SDK
primitives are counted as normal implementation work rather than claimed reusable systems.

## 6. Frozen MVP

```text
24 original collectibles
4 rarities
3 package tiers
1 album
1 soft currency
1 rewarded-ad acceleration point
local/platform save
one-screen core loop
```

Explicit non-goals:

```text
>24 collectibles before first release
shop economy
second currency
daily quests
season pass
live events
multiplayer
3D world
combat
base builder
leaderboard requirement
character upgrades
marketplace
```

If the core reveal only becomes interesting after adding those systems, the candidate has failed the
low-production thesis.

## 7. Working creative direction

**Pocket Gremlins: Mystery Desk Toys** is selected as a concrete production theme for v1 because:

- sealed blister/foil packages naturally support peel/pull/pop interactions;
- tiny desk creatures can share one body/material grammar while remaining visually distinct;
- rarity can be communicated cheaply through material/finish/accessory changes;
- the concept can be original rather than depending on named third-party characters;
- the same engine can be re-themed later if the mechanic works but the creative does not.

Example collectible grammar:

```text
common      -> plain soft-plastic gremlin + one desk-object trait
rare        -> unusual material / stronger silhouette + two traits
epic        -> animated/glow accent or premium accessory
legendary   -> distinctive silhouette + premium reveal treatment
```

This is deliberately **not** a Labubu/dumpling/brainrot clone.

## 8. Monetization hypothesis

MVP monetization must not distort the reveal loop.

Allowed first-release monetization:

- normal platform interstitial placement only at a natural session boundary, if required/appropriate;
- one rewarded-ad acceleration point such as an optional instant premium package / currency boost.

Do not add an ad wall between every package. The first product question is whether players want to
open another item; monetization cannot be allowed to destroy that signal.

## 9. Pre-build kill conditions

Demote to WATCH/SKIP before release if any of the following becomes true:

1. a credible implementation plan no longer fits the frozen `<=7 focused person-days` range;
2. the 24-collectible asset family cannot be produced consistently within the asset budget without
   substantial bespoke illustration/3D work;
3. the unwrap/reveal interaction requires physics or complex animation tooling rather than staged
   pointer interactions;
4. an internal playable prototype cannot make `unwrap -> anticipation -> rarity reveal -> album`
   satisfying without adding a second gameplay system;
5. the chosen theme drifts toward recognizable third-party IP to become appealing.

## 10. Post-launch falsification conditions

The thesis is not “the game will be profitable.” The falsifiable product claim is:

> A cheap original tactile reveal can create enough repeat-opening behavior to justify iterating the
> collectible loop without adding a heavy meta game.

Instrument at minimum:

```text
session_start
package_selected
unwrap_started
unwrap_completed
collectible_revealed
rarity_revealed
album_opened
duplicate_converted
next_package_started
rewarded_ad_offer
rewarded_ad_completed
session_end
```

Also retain platform-provided session/return/revenue signals where available.

Treat the thesis as falsified or strongly weakened if, after a sufficient real traffic cohort:

- the dominant observed behavior is one reveal and exit rather than repeated opening;
- album usage is negligible and collection completion provides no observable continuation signal;
- rewarded monetization is needed merely to make the base loop progress at all;
- additional systems are proposed as the primary remedy for weak reveal/repeat behavior;
- the game only gets meaningful discovery after leaning on unrelated trend/IP keywords.

Absolute retention/revenue thresholds are **not invented in this dossier** because no validated
portfolio baseline exists yet. Freeze those thresholds before interpreting post-launch results once
a real comparable baseline is available.

## 11. Decision

### Portfolio action: BUILD — small probe

```text
market_prior: favorable
production_fit: acceptable
evidence_coverage: medium
decision_validation_status: heuristic
```

Hard gates:

- production fit is not blocking: PASS;
- unresolved critical technical/platform blocker: none known;
- evidence coverage meets initial medium+ heuristic minimum: PASS;
- validated hard negative filter: none exists for this structure.

### Why build

The candidate is one of the few structures in the sweep that combines:

```text
current close-market evidence
+ high reward-loop clarity
+ very low systems burden
+ original-IP feasibility
+ strong AI-assisted asset fit
+ cheap re-themeability
```

The expected cost is small enough that the contradictory market evidence can be resolved more
cheaply by a real release than by building more research infrastructure.

### Why this is not a strong BUILD

Simple opener clones frequently fail, the working theme is unvalidated, and no competitor
retention/revenue data exists. The decision is therefore a **bounded experiment**, not a conviction
bet.

## 12. Next action

Do not add another Reaper subsystem.

The next work item is a production-ready micro-spec for the frozen 24-item MVP, followed by the
actual build only if the micro-spec still fits the `<=7 focused person-days` production envelope.
