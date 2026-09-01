# Production micro-spec v1 — tactile-mystery-collectibles-v1 / candidate v2

Status: **implementation-ready probe contract**  
Decision source: `decision-v2.json`  
Config source: `probe-config-v1.json`  
Target: Yandex Games web build  
Hard production envelope: **<= 7 focused person-days**

This spec does not enlarge the market thesis. If implementation needs a system not listed here,
first assume it is out of scope.

## 1. Product question

The first release exists to answer one behavioral question:

> After one mystery reveal, do real players voluntarily start another package and continue filling
> the collection?

The game is not a case-simulator platform and not a content/liveops framework.

## 2. Frozen loop

```text
choose package
-> one short deterministic pull-tab interaction
-> anticipation beat
-> reveal collectible + rarity
-> mark new item or convert duplicate to soft currency
-> offer immediate next package
-> optionally inspect album
-> repeat
```

No physics. No 3D. No combat. No movement. No level system.

## 3. Implementation stack

Preferred smallest practical stack:

```text
Vite
React
TypeScript strict
plain CSS / CSS modules
React useReducer + small domain functions
Yandex Games SDK wrapper
Yandex Metrica adapter
Vitest for deterministic domain/state tests
```

Do not add Redux, Zustand, XState, Phaser, Pixi, Three.js, a physics library, animation framework,
backend, database, router, component library or generic game framework.

Use DOM/CSS transitions and `requestAnimationFrame` only where the pull-tab needs pointer-following
motion.

## 4. Screens / surfaces

There are only two user surfaces.

### 4.1 Core screen

Always contains:

```text
top-left: game mark / small title
top-right: soft-currency balance + optional rewarded button
center-top: 3 package-tier cards
center: selected physical-looking package
center-bottom: pull tab / interaction affordance
bottom-left: album button + discovered count (X/24)
bottom-center/right: contextual result / Open another action
```

Package cards:

- `Paper Pouch` — FREE;
- `Foil Pack` — 20 coins;
- `Prism Box` — 50 coins.

Paid package cards remain visible when unaffordable. They are disabled and show the missing cost;
never hide the progression target.

### 4.2 Album overlay

Single overlay, not a routed page.

```text
24 fixed slots
rarity grouping or rarity border
discovered item: artwork + name + owned count
undiscovered item: silhouette / question mark
close button
```

No sorting, filters, favorites, lore pages, achievements or completion rewards in v1.

Opening the album pauses gameplay markup. Closing returns to the prior core-screen state.

## 5. Runtime state machine

Use explicit discriminated UI states:

```text
BOOT
READY
PACKAGE_SELECTED
INTERACTING
REVEAL_COMMITTED
REVEALING
RESULT
ALBUM_OPEN
AD_PAUSED
PLATFORM_PAUSED
RECOVERABLE_ERROR
```

### 5.1 BOOT -> READY

Sequence:

1. initialize Yandex Games SDK;
2. initialize safe storage;
3. read/migrate save;
4. preload all UI-critical package/reveal assets and enough collectible assets for first reveal;
5. restore a persisted `pendingReveal` if one exists;
6. render an interactive state;
7. call `LoadingAPI.ready()` only now.

If `pendingReveal` exists, enter `RESULT`/recovery presentation without rolling another item.

### 5.2 READY -> PACKAGE_SELECTED

Player chooses one of three package cards.

Validation:

- free package always selectable;
- paid package selectable only when balance >= cost;
- selection does not deduct currency;
- emit `tm_package_select` once.

### 5.3 PACKAGE_SELECTED -> INTERACTING

Primary input: deterministic horizontal pull tab.

Contract from `probe-config-v1.json`:

```text
visual travel: 56 CSS px
commit threshold: 60%
pointer/touch progress clamps to 0..1
release below threshold -> authored snap-back
release at/above threshold -> commit
```

No velocity, acceleration, inertia, collision or simulated material deformation.

Keyboard fallback:

- focusable interaction control;
- Enter/Space commits the same deterministic interaction;
- no separate keyboard-only reward logic.

On pointer/touch start emit `tm_interaction_start` once for that attempt.
On successful commit emit `tm_interaction_done` once.

Set `touch-action: none` only on the interaction affordance, not globally.

### 5.4 INTERACTING -> REVEAL_COMMITTED

This is the transactional boundary.

On successful commit:

1. revalidate selected tier and balance;
2. deduct cost from a computed next-state object;
3. sample rarity using package probabilities;
4. sample uniformly from catalog items in that rarity;
5. determine `isNew` from owned count;
6. if duplicate, add rarity duplicate value;
7. increment owned count and total reveal count;
8. create `pendingReveal` with the exact sampled result and economic delta;
9. write the **entire next save state once**;
10. only after persistence succeeds, begin reveal animation.

Reloading after commit must never permit rerolling or losing the paid package cost.

If persistence fails before commit is durable, do not consume the package and enter
`RECOVERABLE_ERROR` with retry.

### 5.5 REVEAL_COMMITTED -> REVEALING -> RESULT

Normal reveal timing:

```text
0–180 ms      tab/package close-out
180–450 ms    anticipation shake / seam glow / audio rise
450–800 ms    silhouette / rarity-color preflash
800–1000 ms   collectible resolves
1000–1200 ms  name, rarity, NEW/DUPLICATE treatment
1200 ms        result controls enabled
```

Legendary may extend result-control enable to 1500 ms and add a unique accent/sound. Do not build a
second animation system for legendary.

At reveal:

- emit `tm_collectible_reveal`;
- emit `tm_rarity_reveal`;
- if duplicate, emit `tm_duplicate_convert`;
- display exact duplicate coin award;
- show `NEW!` only on first discovery.

Result actions:

- primary: `Open another`;
- secondary: `Album`.

Pressing `Open another` emits `tm_next_package`, clears `pendingReveal`, persists, and returns to
READY with the previous package tier still selected if affordable; otherwise select Paper Pouch.

Opening Album also clears/persists `pendingReveal` because the result has been acknowledged.

## 6. RNG and economy

`probe-config-v1.json` is authoritative.

### 6.1 Package economy

| Package | Cost | Common | Rare | Epic | Legendary |
|---|---:|---:|---:|---:|---:|
| Paper Pouch | 0 | 74% | 22% | 3.5% | 0.5% |
| Foil Pack | 20 | 45% | 40% | 13% | 2% |
| Prism Box | 50 | 15% | 45% | 32% | 8% |

Paper Pouch is permanently free. This prevents the experiment from turning into an economy gate.

### 6.2 Duplicate conversion

```text
common -> 4 coins
rare -> 8 coins
epic -> 18 coins
legendary -> 45 coins
```

New collectibles grant no coins.

There is exactly one currency. No purchase store, generators, idle income, daily bonus or timed
currency faucet.

### 6.3 RNG implementation

Use a small pure domain function:

```text
rollRarity(packageId, random01)
rollItem(rarity, random01)
```

Production randomness may use `crypto.getRandomValues()` mapped to `[0,1)`.
Tests inject deterministic values.

No pity system, guaranteed-new mechanic, reroll button or paid probability modifier in v1.

## 7. Rewarded advertisement

Single acceleration point only.

Availability:

```text
hidden/disabled until 3 collectible reveals
then available if at least 5 reveals have occurred since the previous rewarded grant
```

CTA: `Watch ad · +20`.

Behavior:

1. emit `tm_reward_offer` when player explicitly presses CTA;
2. pause gameplay/audio;
3. call rewarded video SDK method;
4. grant exactly +20 coins **only inside `onRewarded`**;
5. save immediately after granting;
6. emit `tm_reward_done` only after the reward is granted;
7. on close/error without `onRewarded`, grant nothing;
8. resume the prior UI state when platform/gameplay state allows.

Do not show manual fullscreen/interstitial ads in the first behavioral probe. Yandex may show its
platform startup fullscreen ad; the game must handle platform pause/resume correctly.

Do not use sticky banners in v1; the compact interaction surface has too much accidental-click
risk and the behavioral experiment does not need them.

## 8. Save contract

No backend and no login requirement.

Primary production storage: `ysdk.getStorage()` / Yandex safe storage abstraction.
Cloud cross-device player saves are out of scope for the first probe.

Single key:

```text
pocket_gremlins_save_v1
```

Schema:

```ts
type SaveV1 = {
  schemaVersion: 1;
  softCurrency: number;
  owned: Record<CollectibleId, number>;
  totalReveals: number;
  revealsSinceReward: number;
  lastSelectedPackageId: PackageId;
  pendingReveal: null | {
    openIndex: number;
    packageId: PackageId;
    itemId: CollectibleId;
    rarity: Rarity;
    isNew: boolean;
    duplicateCoins: number;
  };
};
```

Rules:

- unknown/missing fields migrate to safe defaults;
- impossible negative balances clamp to zero and log a recoverable diagnostic;
- unknown catalog IDs in `owned` are preserved during migration but ignored by current UI;
- malformed JSON resets only after keeping an in-memory diagnostic copy for the session;
- every committed reveal and rewarded grant writes immediately;
- album open/close alone does not require a save unless it acknowledges `pendingReveal`;
- no write loop/timer.

For local non-Yandex development only, a localStorage adapter may implement the same interface.
Release build uses the Yandex storage adapter.

## 9. Yandex Games lifecycle contract

Checked against current official Yandex Games SDK documentation on 2026-09-01.

### 9.1 SDK / loading

- SDK integration is mandatory for publication;
- call `LoadingAPI.ready()` only when the game is actually interactive and loading UI is gone;
- do not call it on a fixed timeout.

### 9.2 Gameplay markup

Call `GameplayAPI.start()` when:

- core package selection/reveal gameplay becomes active;
- returning from album/menu state;
- gameplay truly resumes after platform/ad pause.

Call `GameplayAPI.stop()` when:

- album overlay opens;
- rewarded ad is about to display;
- platform pauses gameplay/tab visibility;
- gameplay otherwise becomes non-interactive.

The UI state and gameplay markup must agree; do not mark gameplay active while an ad/menu is open.

### 9.3 Pause/resume events

Subscribe to `game_api_pause` and `game_api_resume`.

On pause:

- mute audio;
- freeze reveal timers/interaction input;
- preserve current state;
- do not complete a pull/reveal in the background.

On resume:

- restore audio only after a user interaction if browser policy requires it;
- resume the exact prior state;
- never reroll a committed `pendingReveal`.

Yandex may show a fullscreen ad at startup without direct ad callbacks, so these platform events
must work before the first player interaction.

Official references:

- https://yandex.com/dev/games/doc/en/sdk/sdk-game-events
- https://yandex.com/dev/games/doc/en/sdk/sdk-events
- https://yandex.com/dev/games/doc/en/sdk/sdk-adv
- https://yandex.com/dev/games/doc/en/sdk/sdk-player

## 10. Analytics contract

Use a Yandex Metrica tag with JavaScript-event goals for the custom behavioral funnel. Built-in
Yandex Games metrics remain useful for audience/playtime/monetization but do not replace this
candidate-specific funnel.

Goal IDs are frozen in `probe-config-v1.json`:

```text
tm_session_start
tm_package_select
tm_interaction_start
tm_interaction_done
tm_collectible_reveal
tm_rarity_reveal
tm_album_open
tm_duplicate_convert
tm_next_package
tm_reward_offer
tm_reward_done
tm_session_end
```

`tm_session_start` fires once after READY is reached.
`tm_session_end` is best-effort on lifecycle exit/pagehide; do not rely on it for all denominators.

Allowed event parameters, no PII:

```text
package_id
item_id
rarity
is_new
open_index
soft_currency_before
soft_currency_after
owned_unique_count
```

Primary descriptive funnel:

```text
first collectible reveal
-> next_package_started after first reveal
-> second collectible reveal
-> third collectible reveal
-> album_opened
```

Also inspect:

- package-tier choice distribution;
- new vs duplicate progression;
- optional rewarded-ad take rate;
- Yandex built-in playtime/returning-user metrics when enough data exists.

Do **not** invent pass/fail retention or revenue thresholds before a suitable portfolio baseline is
frozen. The first interpretation should explicitly report cohort size and uncertainty.

Yandex Games documentation explicitly points to Yandex Metrica for custom goals/funnels.

Official references:

- https://yandex.com/dev/games/doc/en/concepts/analytics
- https://yandex.com/dev/games/doc/en/concepts/yandex-metrica
- https://yandex.com/support/metrica/en/objects/reachgoal

## 11. Asset contract

Catalog is exactly 24 items from `probe-config-v1.json`:

```text
10 common
7 rare
5 epic
2 legendary
```

### 11.1 Shared visual grammar

All collectibles are small original desk-creature toys with:

- one of 3–4 reusable body silhouettes;
- consistent face/eye grammar;
- one dominant desk-object motif;
- one material/finish family;
- transparent background master;
- readable silhouette at thumbnail/card size.

Do not generate 24 unrelated art styles.

### 11.2 Rarity treatment

```text
common    -> matte/base plastic, restrained border
rare      -> stronger material variation + border accent
epic      -> premium accessory + glow/animated accent
legendary -> unique silhouette emphasis + unique reveal accent
```

Rarity must remain legible without relying only on color: label + border/icon + motion/sound
intensity.

### 11.3 Deliverables

For each collectible:

```text
1 transparent master image
1 optimized runtime WebP/PNG
stable item ID matching config
```

Package art:

```text
paper_pouch
foil_pack
prism_box
```

Use one shared package layout with material/color differences rather than three unrelated designs.

No 3D models are required.

## 12. Audio / motion

Minimum audio set:

```text
pull / peel
package pop
common reveal
rare reveal
epic reveal
legendary reveal
coin duplicate
UI tap
```

Keep sounds short and layerable.

Motion must respect `prefers-reduced-motion`; reduced-motion mode keeps the state sequence and
rarity information but shortens/shifts animation rather than removing feedback entirely.

Mute on `game_api_pause`, ad open and tab loss.

## 13. Desktop / touch behavior

Minimum tested viewport classes:

```text
360x640 portrait touch
640x360 landscape touch
1280x720 desktop
1920x1080 desktop
```

Requirements:

- core interaction and result fit without mandatory page scrolling;
- package cards remain tappable with >=44 CSS px target size;
- interaction area captures pointer/touch without scrolling the page;
- no global prevention of browser input outside the interaction area;
- mouse and touch use the same domain state transition;
- keyboard Enter/Space can commit the selected package interaction;
- orientation change during non-committed interaction resets visual progress safely;
- orientation change after commit cannot reroll reward.

## 14. Error handling

Recoverable errors must not create alternative progression rules.

Cases:

- storage load failure -> default session state + diagnostic; retry storage when safe;
- save failure before reveal commit -> do not consume package, show retry;
- asset load failure -> placeholder silhouette + retry; state remains valid;
- rewarded ad error/close without reward -> no coins, CTA becomes available after UI recovers;
- Yandex SDK unavailable in local dev -> dev adapter only; release build fails integration QA.

No generic error-reporting platform is required for the probe.

## 15. Required tests

Domain tests:

- package probability boundaries;
- catalog selection constrained to rolled rarity;
- paid package cannot commit without currency;
- cost deduction and duplicate grant applied exactly once;
- new item grants zero duplicate coins;
- pending reveal survives reload without reroll;
- acknowledging result clears pending reveal exactly once;
- rewarded +20 only on rewarded callback;
- rewarded cooldown by reveal count;
- malformed save migration/defaults;
- all package probability sums equal 1;
- catalog counts match configured rarity counts.

Interaction tests/manual QA:

- below-threshold pull snaps back;
- threshold pull commits once even with duplicate pointer events;
- touch/mouse/keyboard reach same commit action;
- ad/platform pause cannot complete reveal in background;
- resume returns to exact committed result;
- album gameplay start/stop markup is correct;
- Metrica goal adapter fires once per domain event.

## 16. Definition of Done

The probe is implementation-ready/releasable only when all are true:

- [ ] exactly 24 original collectible assets exist and match config IDs;
- [ ] exactly three package tiers use the frozen probabilities/costs;
- [ ] Paper Pouch can always be opened for free;
- [ ] one deterministic pull interaction works with mouse/touch/keyboard;
- [ ] reveal sequence clearly communicates item, rarity, new/duplicate and coin delta;
- [ ] pending reveal is transactionally durable before animation;
- [ ] save survives reload and migration tests;
- [ ] album shows 24 slots and owned counts;
- [ ] optional rewarded +20 obeys SDK callback semantics;
- [ ] no manual fullscreen interstitial or sticky banner is added to first probe;
- [ ] `LoadingAPI.ready()` timing passes Yandex debug-panel review;
- [ ] gameplay start/stop + platform pause/resume pass debug-panel review;
- [ ] all 12 custom analytics goals are wired through one adapter;
- [ ] core screen fits minimum target viewports without required page scroll;
- [ ] domain test suite is green;
- [ ] final implementation still plausibly fits <=7 focused person-days;
- [ ] none of the non-goals below slipped into scope.

## 17. Hard non-goals / kill boundary

Do not add:

```text
physics unwrap
3D
character movement
combat
levels
quests
dailies
achievements
leaderboards as a requirement
shop economy
second currency
idle income
pity system
rerolls
marketplace
inventory equipment
upgrades
base building
multiplayer
social systems
season pass
liveops
cloud account/login flow
manual interstitial cadence
sticky banners
>24 launch collectibles
```

If credible implementation requires any of those, stop and re-evaluate rather than silently
expanding the probe.

If the build plan exceeds **7 focused person-days**, the pre-build M2 kill condition is triggered.

## 18. Delivery order

Recommended implementation order:

```text
1. domain config + RNG/economy + save transaction tests
2. static core screen + package selection
3. deterministic pull interaction
4. reveal/result state machine
5. album
6. final 24-asset integration
7. Yandex storage/lifecycle
8. Metrica goals
9. rewarded ad
10. sound/reveal polish
11. touch/desktop/debug-panel QA
12. release
```

Do not front-load secondary polish before the reveal loop works with placeholder assets.
