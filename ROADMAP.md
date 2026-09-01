# Roadmap

`ROADMAP.md` is the sequencing source of truth for the active Yandex Analytics Reaper delivery path.
The detailed roadmap that preceded the `0.2.0` acceptance is preserved verbatim at
[`docs/history/ROADMAP-pre-0.2.0.md`](docs/history/ROADMAP-pre-0.2.0.md).

The project optimizes for **time to evidence-backed low-production opportunities**, not for
infrastructure sophistication.

## Evidence rules

- raw/current evidence and provenance remain authoritative;
- `ratingCount`, search exposure/rank and query supply are proxies, not DAU, revenue, retention,
  CTR, playtime or profitability;
- manual/heuristic decisions must be labeled as such;
- query-family coherence must be inspected before treating a family as one market;
- production burden is a first-class decision variable;
- no new infrastructure milestone may replace a concrete analyst decision loop.

## Delivery path

```text
M0 evidence foundation — COMPLETE
-> M1 analyst workbench / START ANALYSIS — COMPLETE
-> M1.5 Reaper 0.2.0 / Runner v1.2 — COMPLETE
-> M1.6 Mystery / Unboxing / Collection sweep — COMPLETE
-> M2 candidate dossier for tactile-mystery-collectibles-v1 — NEXT
-> FIRST DECISION LOOP
-> only then consider broader discovery automation/calibration where evidence justifies it
```

---

## M0 — Trustworthy evidence foundation — COMPLETE

Completed before the current roadmap revision. The system can collect, replay, normalize, persist
and trace Yandex evidence without silently collapsing source uncertainty.

Historical detail remains in
[`docs/history/ROADMAP-pre-0.2.0.md`](docs/history/ROADMAP-pre-0.2.0.md).

## M1 — Analyst Workbench v0 / `START ANALYSIS` — COMPLETE 2026-08-30

Human-in-the-loop analysis can:

```text
collect real Yandex evidence
-> declare explicit query family / market question
-> construct reproducible comparable set
-> inspect current supply / quality / traction proxies
-> inspect missingness + provenance
-> compare concrete hypotheses
```

Evidence:
[`docs/history/analyst-pilot-2026-08-30.md`](docs/history/analyst-pilot-2026-08-30.md).

## M1.5 — Reaper `0.2.0` / Analyst Experiment Runner v1.2 — COMPLETE 2026-09-01

Delivered:

- immutable run identity and verbatim manifest hash;
- exclusive workdir locking;
- human + structured progress logs and heartbeat;
- deterministic same-workdir `resume`;
- whole-exact-query recovery;
- valid `COMPLETED` query reuse only;
- comparable-first recovery;
- bounded `1..4` exact-query workers, default `4`;
- sequential pagination inside each query;
- isolated query sessions;
- serialized SQLite-affecting persistence;
- deterministic manifest-order assembly;
- crash-safe verified create-only artifact publication;
- final timing/reuse metadata;
- package version `0.2.0`.

Release acceptance passed on a real 15-family / 36-query / 3-page sweep with a deliberate hard kill
followed by same-workdir resume. The resumed run reused four valid completed queries, collected 32,
finished 36/36 and produced a verifier-PASS immutable artifact.

Evidence:
[`docs/history/reaper-0.2.0-acceptance-2026-09-01.md`](docs/history/reaper-0.2.0-acceptance-2026-09-01.md).

No runner redesign, scheduler, daemon, generic DAG, distributed worker layer, dashboard, generic
checkpoint framework or cache layer is currently justified.

## M1.6 — Mystery / Unboxing / Collection opportunity sweep — COMPLETE 2026-09-01

Collection:

- 15 analyst families;
- 36 exact queries;
- three pages;
- clean anonymous RU desktop context;
- 665 unique comparable listings;
- 665 / 665 rich metadata;
- query-family coherence inspected;
- fresh outliers and repeated/reskinned supply inspected;
- representative descriptions/instructions decomposed for production burden;
- reward strength and re-themeability reviewed;
- clone-graveyard counter-evidence explicitly retained.

Research:
[`research/mystery-unboxing-collection-sweep-v1/`](research/mystery-unboxing-collection-sweep-v1/).

### M1.6 decisions

**BUILD / route to M2**

`tactile-mystery-collectibles-v1`

```text
original mystery object
-> 2–4 tactile unwrap/reveal actions
-> anticipation
-> random collectible + rarity
-> album
-> duplicate currency
-> next package
```

Primary observed structural reference:
Yandex Games listing `533677`, «Сквиш Мистери Дамплинги: Открой Пельмень».

This is a **small heuristic BUILD probe**, not a claim of proven profitability.

**WATCH**

`simplified-lucky-object-reveal-v1`

Preserve the lucky-block action -> anticipation -> rarity reward grammar, but remove the expensive
3D Roblox-like world. Current evidence validates the broader fresh lucky-block cluster, not yet the
stripped one-screen implementation.

**SKIP**

- generic real-world-object case simulator;
- low-effort pack-opening reskin factory;
- Standoff/Brawl/IP case-simulator clone;
- full 3D lucky-block/brainrot clone.

Rationale:
[`research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`](research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md).

---

# PRIMARY PATH — M2 / FIRST DECISION LOOP

## M2 — Candidate Dossier v0 — NEXT

M2 starts from the real candidate `tactile-mystery-collectibles-v1`. Do **not** build a generic
dossier platform in the abstract.

### M2.1 — Candidate identity + evidence package

- [ ] version candidate identity;
- [ ] bind it to sweep `mystery-unboxing-collection-sweep-v1 / 20260901T062453Z`;
- [ ] retain supporting evidence, counter-evidence and unknowns;
- [ ] trace market features to the persisted sweep evidence;
- [ ] retain the primary reference and negative controls.

### M2.2 — Production assessment

Freeze a simple candidate-specific rubric covering:

```text
core engineering
asset generation
content count
backend
balancing
liveops
QA
mobile adaptation
AI-agent fit
MVP day range
```

For this candidate, aggressively defend the MVP boundary:

```text
24–36 original collectibles
4 rarities
3 package tiers
one album
duplicate currency
one rewarded-ad acceleration point
no multiplayer
no 3D world
no combat
no daily quest system
no shop economy
no liveops framework
```

### M2.3 — Heuristic market prior + decision

- [ ] summarize current supply and relevant benchmark traction proxies;
- [ ] state why search rank/breadth is not demand;
- [ ] state the counter-evidence from weak simple reskins;
- [ ] score reward strength and re-themeability explicitly;
- [ ] assign production-risk range;
- [ ] produce a traceable `BUILD / WATCH / SKIP` decision;
- [ ] keep the decision labeled `heuristic` until real post-launch evidence exists.

### `FIRST DECISION LOOP` gate

Reached when one real candidate can travel end to end through:

```text
candidate identity
-> exact evidence package
-> production assessment
-> heuristic market prior
-> explicit counter-evidence
-> BUILD / WATCH / SKIP
```

---

# After M2 — deferred until decision-loop evidence justifies it

Potential later work remains valid but is not automatically next:

- broader candidate discovery automation;
- taxonomy validation/classification;
- historical backtesting;
- external trend sources;
- portfolio calibration;
- dashboards/scheduling;
- automated ranking.

Promote any of these only if the M2 decision loop exposes a concrete bottleneck they solve.

## Current sequencing guard

Until `tactile-mystery-collectibles-v1` completes M2, reject work that primarily adds:

```text
another runner redesign
scheduler
dashboard
generic orchestration framework
taxonomy expansion
ML/ranking
broad external-source integration
```

The current job is to decide whether a **very cheap, original, reward-first collectible opener**
deserves a real build/release test.
