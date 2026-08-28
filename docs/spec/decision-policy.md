# Candidate Decision Policy

Decision values:

```text
BUILD
WATCH
SKIP
```

They are portfolio actions, not claims of objective market truth.

## Decision validation status

Every decision declares how mature the policy/evidence is:

```text
heuristic
backtest_validated
portfolio_calibrated
```

Phase 4 decisions are `heuristic` by default. A decision policy may be promoted only after the relevant validation/calibration phase supports it.

## Separate qualitative dimensions

Do not reuse one enum for unrelated concepts.

### Market prior

```text
strong_favorable
favorable
mixed
unfavorable
strong_unfavorable
unknown
```

### Production fit

```text
strong
acceptable
weak
blocking
unknown
```

### Evidence coverage

```text
high
medium
low
insufficient
```

## Hard gates before BUILD

Initial hard gates:

```text
production fit is not blocking
no unresolved critical technical/platform blocker
evidence coverage meets the current policy minimum
no validated hard negative filter is triggered
```

Novelty/differentiation is evidence, not an undefined binary hard gate unless a future platform rule makes it one.

## BUILD

Use when the current policy judges the market prior sufficiently favorable, production fit acceptable/strong, evidence coverage adequate, and no hard blocker/validated negative rule exists.

Required record:

```text
why build
top supporting evidence
top counter-evidence
unknowns
expected MVP scope
thesis falsification conditions after launch
decision_validation_status
```

## WATCH

Use when the candidate is potentially attractive but evidence is unstable, incomplete, or contradictory.

Every WATCH decision must contain:

```text
review_at or explicit event trigger
additional_data_needed
conditions that promote to BUILD
conditions that demote to SKIP
```

## SKIP

Use when a structural production constraint fails, a validated negative pattern is triggered, evidence is strongly unfavorable, or expected upside does not justify current cost.

Store:

```text
skip_reason
whether the reason is structural or reversible
conditions that can reopen the candidate
```

## Evidence coverage policy

Initial heuristic policy may require at least:

```text
market evidence: medium+
production assessment confidence: sufficient for an actionable range
overall evidence coverage: medium+
```

Exact thresholds are versioned policy parameters and later subject to backtest/portfolio calibration.

## Numeric scores

A score may later exist for sorting only if it:

```text
is decomposable
preserves uncertainty/coverage
never replaces rationale
is calibrated/validated against historical or portfolio outcomes
```

Do not introduce a magic scalar merely to simplify UI or ranking.
