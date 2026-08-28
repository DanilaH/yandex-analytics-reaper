# Production Assessment

Production assessment is candidate-specific. It describes **how hard this concept is for our current workflow to build**, not what the market/game objectively is.

## Current portfolio constraint

Initial strategy prefers a polished MVP plausibly deliverable in **<= 7 focused person-days total**, including:

```text
engineering
integration
content/assets
QA/rework
Yandex adaptation
release preparation
```

This is a portfolio constraint, not a market fact.

## Assessment dimensions

```text
dev_complexity: xs / s / m / l / xl
asset_burden: low / medium / high
content_burden: low / medium / high
backend_burden: none / low / high
balancing_burden: low / medium / high
liveops_burden: low / medium / high
qa_burden: low / medium / high
mobile_adaptation_burden: low / medium / high
ai_assisted_fit: strong / medium / weak
```

Also store:

```text
estimated_mvp_days_low
estimated_mvp_days_high
major_technical_risks[]
reusable_systems_available[]
assessment_version
tooling_profile
```

## Rubric requirement

Agents must not assign burden labels by intuition alone. Every controlled dimension requires a small versioned rubric before it is used for decisions.

Example:

```text
content_burden

low
→ small finite content set; value mostly comes from reusable systems/procedural repetition

medium
→ meaningful authored levels/assets are required, but one MVP content set is manageable

high
→ game value depends on a large authored content volume or ongoing content production
```

Equivalent rubrics must be written for asset, QA, balancing, backend, liveops, mobile adaptation, and AI-assisted fit before automated/agent assessment is trusted.

## Calibration

Before development, freeze the production assessment used for the decision.

After release compare:

```text
predicted vs actual person-days
predicted vs actual asset/content work
predicted QA burden vs bugs/rework
predicted technical risks vs realized issues
```

Periodic calibration may create a new assessment/rubric version. Do not silently rewrite old predictions.
