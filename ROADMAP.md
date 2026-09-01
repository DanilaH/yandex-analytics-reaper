# Roadmap

`ROADMAP.md` is the sequencing source of truth for the active Yandex Analytics Reaper delivery path.
The detailed pre-`0.2.0` roadmap is preserved verbatim at
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
- no new infrastructure milestone may replace a concrete market/build decision loop.

## Delivery path

```text
M0 evidence foundation — COMPLETE
-> M1 analyst workbench / START ANALYSIS — COMPLETE
-> M1.5 Reaper 0.2.0 / Runner v1.2 — COMPLETE
-> M1.6 Mystery / Unboxing / Collection sweep — COMPLETE
-> M2 candidate dossier / FIRST DECISION LOOP — COMPLETE
-> production-ready micro-spec for tactile-mystery-collectibles-v1 v2 — NEXT
-> cheapest credible build/release probe
-> observe real behavior
-> calibrate or kill the thesis
```

---

## M0 — Trustworthy evidence foundation — COMPLETE

The system can collect, replay, normalize, persist and trace Yandex evidence without silently
collapsing source uncertainty.

Historical detail:
[`docs/history/ROADMAP-pre-0.2.0.md`](docs/history/ROADMAP-pre-0.2.0.md).

## M1 — Analyst Workbench v0 / `START ANALYSIS` — COMPLETE 2026-08-30

Human-in-the-loop analysis can collect real evidence, declare explicit query families, build
reproducible comparables, inspect supply/traction proxies and trace results back to provenance.

Evidence:
[`docs/history/analyst-pilot-2026-08-30.md`](docs/history/analyst-pilot-2026-08-30.md).

## M1.5 — Reaper `0.2.0` / Analyst Experiment Runner v1.2 — COMPLETE 2026-09-01

Delivered and accepted:

- immutable run identity + manifest hash;
- exclusive workdir locking;
- progress logs/events + heartbeat;
- deterministic same-workdir resume;
- completed-query reuse and stale interrupted-run rejection;
- comparable-first recovery;
- bounded `1..4` exact-query workers, default `4`;
- sequential pagination within each query;
- isolated query sessions;
- serialized SQLite-affecting persistence;
- deterministic manifest-order assembly;
- crash-safe verified create-only artifact publication;
- final timing/reuse metadata;
- package version `0.2.0`.

Real acceptance used 15 families / 36 exact queries / 3 pages, deliberately hard-killed the first
invocation, resumed the same workdir with four workers, reused four valid completed queries,
collected 32, finished 36/36 and produced verifier PASS.

Evidence:
[`docs/history/reaper-0.2.0-acceptance-2026-09-01.md`](docs/history/reaper-0.2.0-acceptance-2026-09-01.md).

No runner redesign, scheduler, daemon, generic DAG, distributed worker layer, dashboard, generic
checkpoint framework or cache layer is currently justified.

## M1.6 — Mystery / Unboxing / Collection opportunity sweep — COMPLETE 2026-09-01

Collection:

```text
15 analyst families
36 exact queries
3 pages
clean anonymous RU desktop
665 unique listings
665 / 665 rich metadata
```

The analysis inspected family coherence, fresh outliers, developer/reskin supply, representative
gameplay descriptions, production burden, reward strength, re-themeability and negative controls.

Research:
[`research/mystery-unboxing-collection-sweep-v1/`](research/mystery-unboxing-collection-sweep-v1/).

### M1.6 decisions

**BUILD / route to M2:** `tactile-mystery-collectibles-v1`.

Current corrected candidate grammar after public-page review:

```text
original mystery package
-> one short deterministic pointer/touch interaction
-> anticipation
-> random collectible + obvious rarity
-> album / duplicate currency
-> next package
```

The earlier speculative 2–4-action tactile sequence is superseded. Direct inspection of primary
reference listing `533677` supports a much lower-input choose/open/random-reveal/collection loop.

**WATCH:** `simplified-lucky-object-reveal-v1` — preserve the lucky-object anticipation/rarity
grammar while removing the expensive 3D world; current evidence does not yet validate that stripped
implementation.

**SKIP:** generic real-object case simulator, low-effort pack-opening reskin factory,
Standoff/Brawl/IP case clone, and full 3D lucky-block/brainrot clone.

Rationale:
[`research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`](research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md).

---

# M2 / FIRST DECISION LOOP — COMPLETE 2026-09-01

Candidate:
`research/candidates/tactile-mystery-collectibles-v1/`.

Current decision version: **v2**.

```text
decision: BUILD
scope: small_probe
market_prior: favorable
production_fit: strong
evidence_coverage: medium
decision_validation_status: heuristic
estimated_mvp_days: 4.5–6.5 focused person-days
```

### M2.1 — Candidate identity + evidence package — COMPLETE

- [x] version candidate identity;
- [x] bind it to sweep `mystery-unboxing-collection-sweep-v1 / 20260901T062453Z`;
- [x] retain supporting evidence, counter-evidence and unknowns;
- [x] trace market features to persisted sweep evidence;
- [x] retain primary reference and negative controls;
- [x] preserve superseded v1 candidate/dossier/decision as audit history.

Current identity:
[`research/candidates/tactile-mystery-collectibles-v1/candidate-v2.json`](research/candidates/tactile-mystery-collectibles-v1/candidate-v2.json).

### M2.2 — Production assessment — COMPLETE

Frozen rubric:
[`research/candidates/tactile-mystery-collectibles-v1/production-rubric-v1.md`](research/candidates/tactile-mystery-collectibles-v1/production-rubric-v1.md).

Frozen v2 scope:

```text
24 original collectibles
4 rarities
3 package tiers
one album
one soft currency
one deterministic package interaction
one rewarded-ad acceleration point
no multiplayer
no 3D world
no combat
no daily quests
no shop economy
no liveops framework
```

Production estimate: **4.5–6.5 focused person-days**.

Primary risk is reveal/asset quality, not software architecture. Physics or complex bespoke
animation is a scope failure.

### M2.3 — Heuristic market prior + decision — COMPLETE

- [x] current supply and benchmark traction proxies summarized;
- [x] search breadth/rank explicitly rejected as a demand metric;
- [x] weak simple-opener/reskin counter-evidence retained;
- [x] production/reward/re-themeability tradeoffs stated;
- [x] pre-build kill and post-launch falsification conditions frozen;
- [x] BUILD/WATCH/SKIP action recorded as `heuristic`;
- [x] claim-by-claim evidence reconstruction path provided.

Current dossier:
[`research/candidates/tactile-mystery-collectibles-v1/dossier-v2.md`](research/candidates/tactile-mystery-collectibles-v1/dossier-v2.md).

Machine-readable decision:
[`research/candidates/tactile-mystery-collectibles-v1/decision-v2.json`](research/candidates/tactile-mystery-collectibles-v1/decision-v2.json).

Evidence reconstruction:
[`research/candidates/tactile-mystery-collectibles-v1/evidence-index-v2.md`](research/candidates/tactile-mystery-collectibles-v1/evidence-index-v2.md).

### `FIRST DECISION LOOP` gate — REACHED 2026-09-01

```text
candidate identity
-> exact evidence package
-> production assessment
-> heuristic market prior
-> explicit counter-evidence
-> BUILD / WATCH / SKIP
```

The loop produced a **BUILD — small probe**, not a profitability claim.

---

# PRIMARY PATH — BUILD PROBE

## P1 — Production-ready micro-spec — NEXT

Turn candidate v2 into an implementation-ready spec without increasing the market thesis scope.

Required output:

- exact screen/state model;
- exact opening/reveal state machine;
- rarity probabilities and package costs sufficient for MVP;
- duplicate conversion rules;
- 24-item asset grammar and rarity treatment;
- save contract;
- Yandex lifecycle/ad boundaries;
- minimum analytics events already frozen by dossier v2;
- desktop/touch behavior;
- explicit Definition of Done;
- explicit non-goals and 7-day kill boundary.

The spec must preserve the single deterministic interaction. Do not introduce physics, 3D,
quests, shop/meta systems, multiplayer or a second currency.

## P2 — Cheapest credible build/release probe

Start only if the final implementation plan remains within the **<=7 focused person-days** hard
portfolio envelope.

The first behavioral question is:

> After one reveal, do real players voluntarily initiate another package and continue filling the
> collection?

If the answer is weak, do not rescue the product by adding a heavy meta game. Kill/re-theme the
hypothesis according to the frozen decision conditions.

---

# Deferred until real build evidence justifies it

Potential later work remains valid but is not automatically next:

- broader candidate discovery automation;
- taxonomy validation/classification;
- historical backtesting;
- external trend sources;
- portfolio calibration;
- dashboards/scheduling;
- automated ranking.

Promote any of these only when the real decision/build loop exposes a concrete bottleneck they
solve.

## Current sequencing guard

Until the v2 micro-spec and cheap build probe are completed, reject work whose main effect is:

```text
another runner redesign
scheduler
dashboard
generic orchestration framework
taxonomy expansion
ML/ranking
broad external-source integration
extra gameplay systems
```

The current job is to test whether a **very cheap, original, reward-first collectible opener** can
produce repeat-opening behavior with real Yandex traffic.
