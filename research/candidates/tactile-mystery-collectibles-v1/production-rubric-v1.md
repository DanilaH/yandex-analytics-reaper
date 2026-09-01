# Production rubric v1 — tactile-mystery-collectibles-v1

Status: frozen for the first pre-build decision.  
Portfolio constraint: polished MVP should plausibly fit within **<=7 focused person-days total**.

This rubric is candidate-specific. Labels describe burden for the current simple web/Yandex-game
workflow, not an objective complexity class for all teams.

## dev_complexity

- `xs` — static/simple UI logic; no custom interaction system; <=1 day core engineering.
- `s` — one-screen stateful game with a small custom interaction/reveal loop; no world simulation,
  pathfinding, combat, multiplayer or backend; roughly 1–2.5 engineering days before final QA.
- `m` — multiple gameplay systems/scenes or meaningful physics/progression integration; roughly
  3–5 engineering days before content/QA.
- `l` — 3D world, complex simulation, networking or many coupled systems; likely breaks the
  seven-day portfolio target.
- `xl` — production architecture/content cannot plausibly fit the current portfolio strategy.

## asset_burden

- `low` — <=12 principal original assets or mostly reusable primitives/treatments.
- `medium` — roughly 13–40 principal original assets sharing one strong grammar, with AI-assisted
  generation/cleanup viable and little bespoke animation.
- `high` — large heterogeneous catalog, authored environments, characters requiring individual
  animation, or asset work that dominates the build.

## content_burden

- `low` — one finite content set; no authored levels; value comes from repeatable systems and a
  small catalog that can ship once.
- `medium` — multiple authored levels/scenarios or a materially larger catalog is needed for the
  MVP to feel complete.
- `high` — ongoing/high-volume authored content is central to value.

## backend_burden

- `none` — local/platform save is sufficient; no custom server authority or shared state.
- `low` — one small custom service is required but gameplay is not server-dependent.
- `high` — accounts, multiplayer, server economy, authoritative progression or substantial ops are
  necessary.

## balancing_burden

- `low` — <=3 package tiers, <=4 rarities and one soft currency; balance can be represented by a
  small inspectable table and tuned in a short QA pass.
- `medium` — several interacting currencies/upgrades/progression systems require repeated tuning.
- `high` — economy/progression is a primary product system with broad parameter interaction.

## liveops_burden

- `low` — no liveops required for MVP; static content can remain useful without events.
- `medium` — recurring content/events are expected soon after launch to sustain the concept.
- `high` — live events/content cadence are core to the product promise.

## qa_burden

- `low` — click/tap flows with little persistent state and no ad/save edge cases.
- `medium` — gesture interactions plus save/reload, duplicate economy, rewarded-ad fallback and
  desktop/touch behavior must be verified across representative devices.
- `high` — network, physics/world state, many scenes or broad device-sensitive behavior create a
  large regression surface.

## mobile_adaptation_burden

- `low` — one responsive screen using pointer/touch events; no camera/keyboard-specific gameplay.
- `medium` — gesture precision/layout differs materially between touch and mouse or several screens
  require device-specific tuning.
- `high` — core controls/world/UI require distinct mobile design or substantial performance work.

## ai_assisted_fit

- `strong` — implementation is conventional and bounded; asset family has one controllable visual
  grammar; repetitive variants/data can be generated/reviewed systematically.
- `medium` — AI can accelerate parts of engineering/assets, but substantial bespoke creative or
  technical work remains.
- `weak` — success depends on difficult bespoke animation, high-end 3D, networking, large authored
  environments or other work poorly compressed by the current agent workflow.

## Scope-break rules

The assessment must be revisited before build if any of these are added:

```text
>24 MVP collectibles without evidence that 24 is insufficient
>3 package tiers
>4 rarities
second gameplay currency
shop economy
quests/dailies
multiplayer
3D movement/world
combat
user-generated content
custom backend
liveops framework
```

A feature cannot be added merely to rescue an unrewarding core reveal loop. If the one-screen
unwrap/reveal/album loop is not satisfying without those systems, the candidate fails its intended
production thesis.
