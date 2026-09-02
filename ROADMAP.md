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
-> M1.7 semantic/directness triage — COMPLETE
-> M2 candidate dossier / FIRST DECISION LOOP — COMPLETE
-> P1 production-ready micro-spec — COMPLETE
-> P2 cheapest credible build/release probe — NEXT PRIMARY PATH
-> observe real behavior
-> calibrate, re-theme or kill the thesis
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

Research:
[`research/mystery-unboxing-collection-sweep-v1/`](research/mystery-unboxing-collection-sweep-v1/).

### M1.6 decisions

**BUILD / route to M2:** `tactile-mystery-collectibles-v1`.

Current corrected grammar:

```text
original mystery package
-> one short deterministic pointer/touch interaction
-> anticipation
-> random collectible + obvious rarity
-> album / duplicate currency
-> next package
```

Direct inspection of primary reference listing `533677` superseded the earlier speculative
2–4-action tactile sequence.

**WATCH:** `simplified-lucky-object-reveal-v1`.

**SKIP:** generic real-object case simulator, low-effort pack-opening reskin factory,
Standoff/Brawl/IP case clone, and full 3D lucky-block/brainrot clone.

Rationale:
[`research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md`](research/mystery-unboxing-collection-sweep-v1/opportunity-decomposition.md).

## M1.7 — Semantic / directness triage — COMPLETE 2026-09-02

Later thesis-oriented sweeps exposed a repeated operational bottleneck: Yandex search is fuzzy
enough that a large search union can contain many semantically irrelevant listings, while the rich
metadata path already stores description/instruction/category/tag evidence that is not surfaced in
the analyst export.

M1.7 is a **narrow bottleneck fix**, not a return to broad taxonomy work.

Scope:

```text
frozen AnalystSnapshotReport
+ versioned mechanic × theme thesis terms
+ existing catalogue.get_games raw metadata
-> reproducible semantic corpus
-> theme/mechanic/reward lexical evidence
-> direct_candidate / adjacent_candidate / noise_candidate / insufficient_evidence
-> evidence snippets + raw provenance
```

Constraints:

- no new Yandex endpoint or broad collection source;
- no embeddings/LLM/API dependency;
- no opaque opportunity/directness score;
- no claim that lexical `direct_candidate` is a confirmed gameplay competitor;
- no rewrite of comparable-set v1 or historical taxonomy;
- no SQLite/domain schema migration solely to carry source-specific descriptive text;
- the artifact must replay frozen raw evidence and remain hash-verifiable;
- P2 remains the next primary product path.

Specification:
[`docs/spec/analyst-semantic-enrichment.md`](docs/spec/analyst-semantic-enrichment.md).

Real-data validation:
[`research/semantic-directness-v1/validation-2026-09-02.md`](research/semantic-directness-v1/validation-2026-09-02.md).

The frozen V3 `custom-headphones` set demonstrated the intended operational gain:

```text
312 fuzzy listings
-> 243 noise_candidate
-> 67 adjacent_candidate
-> 2 direct_candidate
-> 0 meaningful direct matches after contextual review of frozen descriptions/instructions
```

This is review-queue reduction, not a market-size or absolute-absence claim.

Definition of Done:

- [x] versioned semantic thesis declaration;
- [x] frozen `get_games` semantic corpus replay;
- [x] transparent dimension matching + evidence snippets;
- [x] conservative candidate-level directness labels;
- [x] deterministic JSON report + analyst-readable CSV;
- [x] CLI entry point;
- [x] focused replay/classification tests pass in CI;
- [x] full repository quality gate passes;
- [x] one real thesis artifact demonstrates useful reduction of fuzzy search noise;
- [x] decision methodology is synchronized with the shipped contract.

---

# M2 / FIRST DECISION LOOP — COMPLETE 2026-09-01

Candidate directory:
[`research/candidates/tactile-mystery-collectibles-v1/`](research/candidates/tactile-mystery-collectibles-v1/).

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

Completed:

- [x] versioned candidate identity;
- [x] exact sweep/run binding;
- [x] supporting evidence, counter-evidence and unknowns;
- [x] claim-by-claim reconstruction path;
- [x] primary reference + negative controls;
- [x] candidate-specific production rubric;
- [x] frozen production estimate and kill conditions;
- [x] visual/public-page correction from candidate v1 -> v2;
- [x] heuristic BUILD/WATCH/SKIP decision;
- [x] superseded v1 artifacts retained as audit history.

Current artifacts:

- [`candidate-v2.json`](research/candidates/tactile-mystery-collectibles-v1/candidate-v2.json)
- [`dossier-v2.md`](research/candidates/tactile-mystery-collectibles-v1/dossier-v2.md)
- [`decision-v2.json`](research/candidates/tactile-mystery-collectibles-v1/decision-v2.json)
- [`evidence-index-v2.md`](research/candidates/tactile-mystery-collectibles-v1/evidence-index-v2.md)

### `FIRST DECISION LOOP` gate — REACHED 2026-09-01

```text
candidate identity
-> exact evidence package
-> production assessment
-> heuristic market prior
-> explicit counter-evidence
-> BUILD / WATCH / SKIP
```

The result is a **BUILD — small probe**, not a profitability claim.

---

# PRIMARY PATH — BUILD PROBE

## P1 — Production-ready micro-spec — COMPLETE 2026-09-01

Frozen implementation artifacts:

- [`implementation-spec-v1.md`](research/candidates/tactile-mystery-collectibles-v1/implementation-spec-v1.md)
- [`probe-config-v1.json`](research/candidates/tactile-mystery-collectibles-v1/probe-config-v1.json)
- [`implementation-review-v1.md`](research/candidates/tactile-mystery-collectibles-v1/implementation-review-v1.md)

The implementation contract freezes:

```text
24 original collectibles
4 rarities
3 package tiers
Paper Pouch always free
one soft currency
one deterministic pull-tab interaction
transactional pendingReveal save
one optional rewarded +20 acceleration point
no manual fullscreen interstitial in the first probe
Yandex safe storage
Yandex loading/gameplay/pause-resume boundaries
12 custom Metrica funnel goals
mouse + touch + keyboard
<=7 focused-day hard kill boundary
```

Independent implementation-readiness review: **PASS**.

Mandatory before producing all 24 final assets: integrate a four-item representative asset spike
(common/rare/epic/legendary) into the actual reveal UI and verify that the production method scales
inside the frozen art/time budget.

## P2 — Cheapest credible build/release probe — NEXT

Start only in a concrete game repository/worktree. Do not put the game implementation inside the
Reaper research codebase.

Recommended stack remains deliberately small:

```text
Vite
React
TypeScript strict
plain CSS/CSS modules
useReducer + pure domain functions
Yandex Games SDK adapter
Yandex Metrica adapter
Vitest domain tests
```

The first behavioral question is:

> After one reveal, do real players voluntarily initiate another package and continue filling the
> collection?

Pre-build stop conditions:

- credible plan exceeds 7 focused person-days;
- 4-item asset spike cannot establish one coherent original family cheaply;
- implementation needs physics/3D/complex bespoke animation;
- reveal is not satisfying without adding a second gameplay system;
- creative requires recognizable third-party IP.

If the released loop is weak, do not rescue it by adding a heavy meta game. Re-theme or kill the
hypothesis according to the frozen M2 conditions.

---

# Deferred until real build evidence justifies it

Potential later work remains valid but is not automatically next:

- broader candidate discovery automation;
- broad taxonomy validation/classification beyond the narrow M1.7 triage contract;
- historical backtesting;
- external trend sources;
- portfolio calibration;
- dashboards/scheduling;
- automated ranking.

Promote any of these only when the real decision/build loop exposes a concrete bottleneck they
solve.

## Current sequencing guard

Until the cheap v2 build/release probe is completed, reject work whose main effect is:

```text
another runner redesign
scheduler
dashboard
generic orchestration framework
taxonomy expansion beyond the approved M1.7 directness triage
ML/ranking
broad external-source integration
extra gameplay/meta systems
```

M1.7 is allowed only because it reuses already-collected evidence to remove a repeated manual
classification bottleneck. It must not grow into generic taxonomy infrastructure or delay P2.

The primary product job is still to test whether a **very cheap, original, reward-first collectible
opener** can produce repeat-opening behavior with real Yandex traffic.
