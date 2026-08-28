# Historical Backtesting

## What the backtest can prove

A historical market backtest can support:

> Games released into market states with feature pattern X historically had better observed outcomes.

It cannot by itself prove:

> If we build this concept, our probability of success is X%.

Historical data contains only concepts somebody chose to release, and outcomes also depend on execution. Treat this as selection bias + execution confounding.

## Split the problem

### Market Prior

Uses only information available before launch:

```text
comparable supply/recent supply growth
peer quality
peer traction proxies
failure/survival history
theme/trend evidence available by the decision time
```

This is relevant to BUILD/WATCH/SKIP.

### Execution Outcome

Uses post-launch information such as the candidate game's own gqRating, rating velocity, load time, updates, monetization, and early traction. It explains published-game outcomes but must not masquerade as pre-build evidence.

## Evidence modes

```text
STRICT_POINT_IN_TIME
Only evidence whose historical availability can be proved and whose `available_at <= decision_as_of`.

RETROSPECTIVE_RECONSTRUCTION
Later/current metadata is used to infer what the concept probably was.
```

Only strict point-in-time results validate production pre-build evidence.

## Candidate concept reconstruction

Preferred evidence order:

```text
launch-time snapshot
first-seen platform snapshot
archived first-version metadata
```

If only eventual/current metadata exists, the run is retrospective. Do not reconstruct production burden from the finished game and pretend it was known before development.

## Historical source integrity

Every historical metric used by the backtest must expose the Evidence Model dimensions, especially:

```text
available_at
historical_availability
revision_status
```

Retroactively recalculated/reconstructed values are not allowed as strict features unless their historical availability can independently be established.

## Platform policy regimes

Do not apply current platform rules blindly to older cohorts. Version relevant platform regimes by effective interval, including where evidence exists:

```text
rating formation/threshold rules
unpublish windows
New/featuring behavior
ranking/moderation rules relevant to outcomes
```

Unknown historical policy remains uncertain rather than silently inheriting today's rule.

## Outcome labels

Avoid one binary `winner` flag. Candidate outcomes may include:

```text
survival_60d
survival_180d
cohort-relative quality strength
traction_30d
traction_90d
breakout
durable traction
```

Thresholds must be versioned and selected before final holdout evaluation.

## Failure cause and censoring

Do not treat every disappearance as low quality.

Possible reasons:

```text
low_quality
rating_absent
developer_removed
policy
copyright
duplicate
technical
unknown
```

Unknown/unresolved outcomes may require censoring rather than a negative label.

## Decision horizon

Do not hardcode only `T - 7d` as a universal truth. Where data permits, evaluate at least:

```text
7d
14d
30d
```

Seven days is especially relevant to the current short-build portfolio strategy, but horizon sensitivity should be measured.

## Comparable-game sets

Use versioned query-family union + taxonomy/similarity rules, not one search-result count.

Store:

```text
comparable_set_version
selection_rule
listing IDs
as_of
```

## Leakage controls

Every feature query enforces `available_at <= decision_as_of`.

Where feasible, track obvious near-duplicate/template/reskin families. Similar templates from the same production family must not create misleading train/holdout separation. Developer-history effects are evaluated separately from the market-only model.

## BacktestSpec freeze

Before evaluating the final holdout, freeze a versioned `BacktestSpec` containing:

```text
feature definitions
candidate reconstruction rules
cohort/outcome definitions
missingness rules
decision horizons
temporal split
metrics
baseline definitions
thresholds
```

After final holdout results are inspected, changes require a new spec and a new untouched future holdout period. Do not tune repeatedly on the same holdout.

## Temporal split

Never random-split across time. Initial ranges may follow the available historical dataset, but development/validation/final holdout must remain chronological.

## Baselines

Before complex models compare against:

```text
random
least supply
highest peer quality
highest peer traction
simple hand-authored rules
```

## Evaluation

For ranking:

```text
precision@K
NDCG@K
lift vs random
lift vs simple heuristics
```

For probability-like models if introduced later:

```text
PR-AUC
Brier score
calibration
```

The main question is whether top recommendations beat transparent simple baselines on an untouched temporal holdout.

## First useful backtest

Start small enough to audit:

```text
500–2000 historical games
5–10 validated gameplay archetypes
market-only features
3 main outcomes:
  survival_60d
  top-quartile quality
  top-quartile traction_90d
```

Prefer interpretable models and validated negative filters before sophisticated ranking systems.
