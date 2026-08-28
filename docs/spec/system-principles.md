# System Principles

This is a living analytical specification. Implementation sequencing is owned by `/ROADMAP.md`.

## Objective

The system has two distinct jobs:

```text
OPPORTUNITY DISCOVERY
market → candidate ideas

CANDIDATE EVALUATION
candidate → evidence → BUILD / WATCH / SKIP
```

It must not claim an exact probability of commercial success before launch.

The pre-build decision decomposes into:

```text
MARKET PRIOR
How favorable is the observed market state for this gameplay/theme hypothesis?

PRODUCTION ASSESSMENT
Can we build a polished version within our current constraints?

EVIDENCE QUALITY
How trustworthy, complete, timely, and historically valid is the evidence?
```

Post-launch execution/outcome is a separate layer used for calibration.

## Non-negotiable analytical rules

1. Raw source evidence is preserved before interpretation.
2. Source response shapes are isolated behind source parsers/DTOs.
3. Domain observations are produced by explicit versioned normalizers.
4. Decision evidence is traceable to source observations/raw snapshots.
5. Observed, estimated, derived, and inferred values remain distinguishable.
6. Missing/unknown values never silently become negative/false/zero.
7. Search-result counts are discovery/supply signals, not canonical competitor counts.
8. Sponsored/editorial exposure is never treated as organic recommendation strength.
9. Taxonomy describes the market/game; production assessment describes our implementation burden.
10. Historical backtests must distinguish strict point-in-time evidence from retrospective reconstruction.
11. No opaque opportunity score may replace decomposable evidence/rationale.
12. BUILD/WATCH/SKIP decisions are versioned and explicitly declare whether they are heuristic, backtest-validated, or portfolio-calibrated.
13. Our own releases are the strongest long-term calibration source.

## Permission/privacy assumption

For this private project:

```text
data collection permission: confirmed externally
tool usage: private/personal
public redistribution/dashboard: not planned
```

These questions are therefore not development blockers for the current project.

## Success boundary

The system is useful before any dashboard or ML platform exists if it can:

```text
observe current Yandex market state
→ identify comparable games consistently
→ surface candidate hypotheses
→ build a traceable evidence dossier
→ make an explicit provisional/validated decision
→ later compare the frozen prediction with real outcomes
```

Do not optimize infrastructure beyond this loop without concrete evidence that it is needed.
