# Yandex Game Market Intelligence — System Principles & Definition of Ready v2

**Snapshot:** 2026-08-28  
**Status:** revised after adversarial review  
**Decision:** ready for repository skeleton and core data-layer implementation.

---

## 1. System objective

The system has two distinct jobs:

```text
A. OPPORTUNITY DISCOVERY
market → candidate ideas

B. CANDIDATE EVALUATION
candidate → evidence → BUILD / WATCH / SKIP
```

It must not claim to predict an exact probability of commercial success before launch.

The pre-build system estimates:

```text
market attractiveness
+
competitive context
+
trend evidence
+
production feasibility
+
monetization fit
+
evidence quality / uncertainty
```

Actual game success also depends on execution quality, retention, polish, developer skill, updates, creative quality, monetization implementation, and platform distribution.

---

## 2. Core analytical decomposition

Do not build one "game success model".

Use four explicit layers:

```text
MARKET PRIOR
How favorable is the market state for this mechanic/theme?

PRODUCTION ASSESSMENT
Can we build a polished version cheaply and quickly?

EVIDENCE QUALITY
How much trustworthy evidence do we actually have?

POST-LAUNCH EXECUTION
How well did the released game actually perform?
```

The production decision uses the first three.

Post-launch data is used for calibration and future learning.

---

## 3. What is technically proven

Live probes on 2026-08-28 confirmed current structured Yandex Games data through:

```text
GET  /games/api/catalogue/v2/feed/
GET  /games/api/catalogue/v2/search
POST /games/api/catalogue/v2/get_games
GET  /games/app/<appID>
```

Confirmed capabilities include:

```text
feed pagination
search pagination
search totalGamesCount
organic/sponsored separation
rich game metadata
Yandex Games Rating (gqRating)
player ratings and star distribution
first/current publication timestamps
version
load-time metadata
platform/language/media metadata
ad / purchase / leaderboard metadata
__playPageData__
```

`playersCount` from older catalogue schemas was not present in current 2026 responses.

---

## 4. Permission/privacy assumption for this project

For this project:

```text
data collection permission has been confirmed externally
tool is private
tool is used only by its owner
no public subscription dashboard is planned
```

Therefore legal/privacy questions are not treated as development blockers in this package.

The architecture still preserves source provenance and access metadata because those are useful operationally and for future source changes.

---

## 5. Definition of Ready gates

### GATE A — capability boundaries exist

The system must depend on capabilities, not one giant source abstraction:

```text
CatalogMetadataProvider
SearchDiscoveryProvider
RecommendationExposureProvider
HistoricalMetricsProvider
StatusHistoryProvider
MediaProvider
TrendProvider
```

One source may implement some capabilities and not others.

### GATE B — raw data is immutable and parser-independent

Required boundary:

```text
RawSnapshot
  ↓
Parser(versioned)
  ↓
NormalizedObservation
  ↓
DerivedFeature
```

Raw snapshots must never depend on parser version.

### GATE C — evidence model is explicit

Every value used in decisions carries:

```text
provenance
measurement_kind
semantic_confidence
freshness
coverage
point_in_time_integrity
uncertainty
lineage
```

No single `confidence_class A-E`.

### GATE D — taxonomy is orthogonal

Taxonomy must separate:

```text
core_loop
objective
meta
session_model
theme
tone
trend_layer
social_mode
presentation
monetization
```

Production cost is NOT part of market taxonomy.

### GATE E — taxonomy is validated before freeze

Correct order:

```text
taxonomy draft
↓
100–200 real Yandex games
↓
manual gold set
↓
confusion analysis
↓
taxonomy revision
↓
freeze v1
```

The repo may implement the draft schema before freeze, but automated decisions must not depend on unvalidated labels.

### GATE F — backtests declare their evidence level

Two modes:

```text
STRICT_POINT_IN_TIME
Only information provably available at decision time.

RETROSPECTIVE_RECONSTRUCTION
Later metadata may be used to infer what the concept probably was.
```

Only `STRICT_POINT_IN_TIME` may be used to claim true pre-build predictive evidence.

### GATE G — no opaque opportunity score

First release must expose component evidence:

```text
market_prior
competition
peer_quality
peer_traction
trend_strength
production_fit
monetization_fit
evidence_coverage
uncertainty
```

A numeric score may be introduced later as a convenience layer only after backtesting and calibration.

### GATE H — explicit decision policy

`BUILD`, `WATCH`, and `SKIP` must have defined meanings, hard gates, and review triggers.

### GATE I — own releases feed back into the system

Every released game must create:

```text
prediction snapshot
actual dev cost
actual moderation result
actual Yandex metrics
actual revenue
prediction error
```

This eventually becomes more valuable than third-party proxies.

---

## 6. What can start now

Ready now:

```text
repository skeleton
source capability interfaces
raw snapshot storage
parser/versioning framework
normalized platform-neutral entities
lineage model
Yandex ingestion adapters
taxonomy draft data structures
probe stability experiments
candidate/evidence schema
```

Not yet worth building deeply:

```text
final taxonomy classifier
ML opportunity model
large historical backtest engine
full dashboard
complex orchestration
large external-source integration set
```

---

## 7. Build order

```text
Phase 1 — Foundation
raw snapshots
capability adapters
normalized entities
lineage
schema drift

Phase 2 — Yandex market state
game metadata
search discovery
feed exposure
status/update/media history

Phase 3 — Taxonomy validation
gold set
taxonomy v2 validation
classifier QA

Phase 4 — Discovery + candidate dossiers
market-state features
candidate generation
BUILD/WATCH/SKIP policy

Phase 5 — Historical backfill
licensed/available historical sources
point-in-time integrity checks

Phase 6 — Backtesting
market-prior validation
negative filters
calibration

Phase 7 — External trend enrichment
Wordstat
YouTube
TGStat
Trends
optional cross-market sources

Phase 8 — Own-game calibration
actual production + Yandex metrics + economics
```

---

## 8. Scope guardrail

The project is successful before any dashboard exists if it can:

```text
1. observe current Yandex market state
2. classify comparable games consistently
3. discover candidate mechanic × theme combinations
4. create an evidence dossier
5. produce BUILD / WATCH / SKIP with traceable reasons
6. later compare that decision with real outcomes
```

Do not optimize infrastructure beyond what supports this loop.
