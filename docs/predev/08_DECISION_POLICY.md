# Candidate Decision Policy v1

## 1. Decision types

```text
BUILD
WATCH
SKIP
```

These are portfolio decisions, not claims of objective market truth.

## 2. Hard gates before BUILD

All must pass:

```text
production scope acceptable
no unresolved critical technical blocker
candidate concept sufficiently distinct
evidence coverage above minimum
no strong validated negative filter
```

## 3. BUILD

Use when market prior is favorable enough, production assessment is strong, evidence coverage is sufficient, and no hard negative evidence exists.

Required output: why build, top supporting evidence, top counter-evidence, unknowns, expected MVP scope, and what would falsify the thesis after launch.

## 4. WATCH

Use when candidate is interesting but evidence is unstable/incomplete. Typical causes include a young accelerating trend, rapidly changing competition, weak history, uncertain third-party estimates, low taxonomy confidence, or mixed evidence.

WATCH must include `review_at`, trigger condition, and additional data needed.

## 5. SKIP

Use when a hard production constraint fails, a validated negative market pattern exists, evidence is strongly unfavorable, or expected upside does not justify cost. Store the reason and which future changes could reopen it.

## 6. Evidence coverage thresholds

Initial categories: high/medium/low/insufficient. BUILD initially requires market evidence medium+, production assessment high, and overall evidence medium+. Calibrate later.

## 7. Decision output shape

A decision contains market prior, production fit, trend strength, competition, evidence coverage, uncertainty, supporting/counter evidence, unknowns, and review triggers.

## 8. No magic score requirement

A numeric score may later be shown for sorting only if it is decomposable, does not hide uncertainty, does not replace rationale, and is backtest-calibrated.
