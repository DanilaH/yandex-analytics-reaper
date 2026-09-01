# Implementation-readiness review v1 — tactile-mystery-collectibles-v1 v2

Review date: 2026-09-01  
Reviewed artifacts: `candidate-v2.json`, `decision-v2.json`, `dossier-v2.md`,
`probe-config-v1.json`, `implementation-spec-v1.md`.

Verdict: **PASS — route to cheapest credible build probe**.

This is not a claim that the game will succeed. It means the implementation contract is specific
enough to build without reopening product scope and remains plausibly inside the <=7 focused-day
portfolio boundary.

## Contract consistency

### Candidate / implementation scope

PASS.

The implementation preserves candidate v2:

```text
one deterministic interaction
anticipation
random collectible + rarity
album / duplicate currency
repeat
```

No physics, 3D, combat, movement, marketplace, quests, liveops, second currency or generic game
framework entered the spec.

### Economy deadlock

PASS.

`Paper Pouch` is permanently free, so progression/repeat behavior is never blocked by currency.
Foil/Prism packages are optional aspirational accelerators funded by duplicates or the one rewarded
acceleration point.

This matters because the experiment is intended to test repeat opening, not monetization pressure.

### Transaction safety

PASS.

The spec samples the result, applies cost/ownership/duplicate delta and persists one next-state with
`pendingReveal` **before** animation. Reload cannot reroll a paid package or apply duplicate currency
twice.

### Analytics ability

PASS with release dependency.

The frozen custom event set can answer the primary repeat-opening funnel through Yandex Metrica.
The game must not ship the behavioral probe without the Metrica tag/goals actually connected;
built-in aggregate metrics alone are insufficient for the candidate-specific funnel.

### Yandex lifecycle / ads

PASS with one implementation note.

The contract uses current documented boundaries:

- actual readiness before `LoadingAPI.ready()`;
- gameplay markup aligned with active gameplay/menu/ad state;
- `game_api_pause` / `game_api_resume` for platform-induced pause/resume;
- rewarded currency only from the rewarded callback;
- no manual fullscreen interstitial/sticky banner in the first probe.

Avoid issuing redundant gameplay start/stop transitions from both platform event handling and local
UI transitions. Platform pause/resume handlers should primarily pause/resume game logic/audio; local
menu/ad boundaries own explicit local markup transitions.

### Production envelope

PASS, but close to the boundary.

The 4.5–6.5 day estimate remains plausible only if the asset family is genuinely AI-assisted and
reuses a tight visual grammar.

The main pre-build risk is not engineering. It is producing 24 coherent original collectibles.

## Mandatory asset spike

Before generating all 24 final collectibles:

1. produce **4 representative masters**: one common, one rare, one epic, one legendary;
2. use the exact shared body/face/material grammar intended for production;
3. integrate them into the actual reveal UI, not a separate moodboard;
4. check readability at runtime card/reveal size;
5. record time spent including cleanup.

Continue to 24 only if:

- all four visibly belong to one product family;
- no named third-party IP is needed to make them appealing;
- the production method extrapolates to the remaining 20 within the candidate's asset budget;
- the legendary can feel special through treatment/composition rather than a bespoke animation
  system.

If this fails, **demote/kill or re-theme before generating 20 more assets**.

## Day-budget sanity check

Reasonable execution budget:

```text
Day 1     domain config, save transaction, state machine, tests
Day 2     core screen, package selection, deterministic pull interaction
Day 3     reveal/result/album + placeholder polish
Day 4     4-asset spike, lock visual grammar, expand asset batch
Day 5     finish asset integration + sound/reveal polish
Day 6     Yandex storage/lifecycle + Metrica + rewarded ad
Day 6–7   touch/desktop QA, debug panel, moderation/release rework
```

This is an execution budget, not a promise. If the plan materially exceeds day 7 before release,
the frozen M2 pre-build kill condition has fired.

## Things explicitly not being validated by this build

- competitor revenue;
- broad case-simulator profitability;
- whether Pocket Gremlins is the optimal theme;
- cloud-save demand;
- manual interstitial monetization;
- large-catalog retention;
- liveops potential.

The build tests the smallest useful uncertainty:

> Is the reveal + rarity + collection transition strong enough to make real users voluntarily open
> another package?

## Final review action

**Proceed to P2 build probe once a concrete game repository/worktree is selected.**

Do not add another Reaper research/infrastructure step before that implementation unless new market
evidence invalidates candidate v2.
