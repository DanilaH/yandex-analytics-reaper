# Opportunity Discovery

Candidate evaluation assumes an idea already exists. Opportunity Discovery generates candidate hypotheses from observed market state.

## Discovery unit

A market seed is:

```text
primary gameplay archetype
×
theme
×
optional trend/cultural entity
```

Production profile is **not** part of the market seed. Production feasibility is applied afterward as a separate screen/assessment.

## Phase 4 — Yandex-native discovery

The first discovery version works without external trend APIs and uses Yandex-native evidence such as:

```text
comparable supply
recent comparable releases / supply growth
peer gqRating distribution
peer rating-count / traction proxies
search-supply observations
known survival/failure evidence where available
observed theme prevalence/change
```

Example transparent patterns:

```text
strong peer quality + non-exploding recent supply
proven archetype + relatively underserved theme
strong recent comparable performance + low production burden after feasibility screen
high failure concentration → avoid/negative candidate signal
```

## Phase 7 — external trend enrichment

Wordstat, YouTube, TGStat, Google Trends and cross-market sources enrich the existing discovery system later.

External trend evidence must not become an implicit prerequisite for the first end-to-end candidate pipeline.

## Pipeline

```text
market-state observations
→ taxonomy aggregation
→ supply/quality/traction-proxy features
→ candidate market seeds
→ dedupe / comparable checks
→ production feasibility screen
→ CandidateConcept
→ deep candidate dossier
```

After Phase 7, external trend evidence can enter before/inside candidate ranking as an additional explicit evidence component.

## Discovery does not equal decision

Discovery produces:

```text
candidate seed
why it surfaced
source feature snapshot/version
```

It does not directly produce BUILD. The candidate must pass the full Decision Policy.

## Initial heuristics

Before historical validation, discovery heuristics are:

```text
transparent
versioned
labeled heuristic
```

They must not be presented as learned predictive rules.

Each heuristic later receives:

```text
historical evaluation
lift vs simple baselines
stability by time/archetype
keep/change/remove decision
```
