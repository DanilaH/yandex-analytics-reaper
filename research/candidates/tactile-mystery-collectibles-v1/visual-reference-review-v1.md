# Visual/reference review v1 — listing 533677

Date checked: 2026-09-01  
Purpose: test whether the primary market reference actually supports the proposed multi-step tactile
interaction, rather than inferring that from the word “unboxing”.

## Sources

Primary current public page:

`https://yandex.ru/games/app/skvish-misteri-damplingi-otkroi-pelmen-533677`

Secondary public promo-image mirror used only as visual context, not evidence authority:

`https://www.puzzlegame.com/Mystery-Squishy-Dumpling-Blind-Box`

## What is actually supported

The current Yandex page describes the interaction as:

```text
choose one of four boxes
-> open it
-> receive a random squishy dumpling
-> rarity/collection progress
-> repeat
```

The page does **not** document a multi-step tearing/peeling/physics interaction. The current public
promo representation also emphasizes an `OPEN` affordance, a hidden/question-mark object and a
large visual rarity contrast between ordinary and exceptional collectibles.

Therefore the market evidence supports:

```text
mystery / unknown state
+ very low input burden
+ anticipation
+ high-contrast rarity reveal
+ collection completion
```

It does **not** currently support the claim that 2–4 tactile manipulation steps are responsible for
engagement.

## Scope correction

The first M2 draft proposed 2–4 tactile unwrap actions. That is unnecessary speculative scope.

Freeze the build hypothesis instead as:

```text
choose package
-> one short deterministic package interaction
-> 0.5–1.5 s anticipation/reveal sequence
-> random collectible + obvious rarity treatment
-> album / duplicate conversion
-> repeat
```

The one interaction may be `pull tab`, `peel seal`, `pop lid`, or a simple click/tap with a staged
package response. It must use pointer/touch primitives and authored transitions, not physics.

The differentiation thesis becomes **better reveal presentation**, not “more interaction steps”.

## Consequence for production assessment

This correction lowers engineering/QA uncertainty and better preserves the <=7 focused-person-day
portfolio constraint. It also creates a cleaner experiment: if the reward/reveal loop is weak, the
project cannot blame a missing secondary gameplay system or a complicated unwrap simulation.

## Evidence status

The public-page check is a current reference inspection, not a replacement for the immutable Reaper
sweep. The sweep remains authoritative for run identity, listing metadata, comparable membership and
market features. This note only constrains how much gameplay complexity may be inferred from the
reference.
