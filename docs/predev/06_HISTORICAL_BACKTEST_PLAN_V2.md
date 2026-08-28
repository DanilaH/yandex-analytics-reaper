# Historical Backtest Plan v2

## 1. What the backtest can and cannot prove

A historical market backtest can support: games released into market states with feature pattern X historically had better observed outcomes.

It cannot by itself prove: if we build this concept, our probability of success is X%.

The historical dataset contains only concepts somebody chose to release, and outcomes also depend on execution. This creates selection bias and execution confounding.

## 2. Split the problem

### Model A — Market Prior

Uses only information available before launch: mechanic/theme market state, competition, peer quality/traction, supply growth, trend signals, failure/survival history. This is relevant to BUILD/WATCH/SKIP.

### Model B — Execution Outcome

Uses post-launch information such as candidate gqRating, rating velocity, load time, updates, monetization, and early traction. This explains published-game outcomes but must not masquerade as pre-build evidence.

## 3. Backtest evidence levels

```text
STRICT_POINT_IN_TIME
Every feature has proof it existed at as_of.

RETROSPECTIVE_RECONSTRUCTION
Later metadata is used to infer concept structure.
```

Only strict point-in-time results validate production pre-build evidence.

## 4. Candidate concept reconstruction

Prefer launch-time snapshot, first-seen platform snapshot, then archived first-version metadata. If only eventual/current metadata exists, label the backtest retrospective. Production scope must not be reconstructed from the finished product as if known pre-build.

## 5. Historical estimate integrity

Every historical third-party metric stores point-in-time integrity: strict point-in-time, immutable historical snapshot, retroactively recalculated, or unknown. Retroactively recalculated data is forbidden as a strict historical feature.

## 6. Platform policy regimes

Do not apply current 2026 platform rules blindly to 2024 games. Store effective interval and relevant rating/unpublish/new-section/ranking/moderation regime. If historical policy is unknown, derived policy outcomes are uncertain.

## 7. Outcome labels

Do not use one winner flag. Track survival_60d, survival_180d, cohort-relative quality strength, traction_30d/90d, breakout, and durable traction where evidence supports them.

## 8. Failure cause

Do not treat every disappearance as low quality. Reasons can include low quality, rating absent, developer removed, policy, copyright, duplicate, technical, or unknown. Unknown cases may need censoring rather than a negative label.

## 9. Market-state features at T-7

Candidate market prior may use comparable active-game count, recent comparable releases, supply growth, peer gqRating distribution, rating-count velocity, valid traction estimates, known failure/deletion rate, developer concentration, monetization prevalence, load-time distribution, and historical theme trend. Every query enforces `as_of_timestamp`.

## 10. Comparable-game construction

Use query-family union + taxonomy match + optional similarity, not one search count. Version the comparable set and store listing IDs and as_of timestamp.

## 11. Developer-history confounding

Maintain a market-only model and a separate market+developer model. BUILD/WATCH/SKIP must not rely on an advantage the portfolio does not yet possess.

## 12. Temporal splits

Never random-split across time. Initial shape if data permits: development 2024-01-01→2025-06-30, validation 2025-07-01→2025-12-31, holdout 2026-01-01→2026-02-28.

## 13. Baselines

Before ML: random, least supply, highest peer quality, highest peer traction, and a simple hand-authored rule set.

## 14. Evaluation

Use precision@K/NDCG@K/lift for ranking and PR-AUC/Brier/calibration for probability-like outputs. The important question is how much better top recommendations are than simple baselines.

## 15. First backtest

Start with 500–2000 historical games, 5–10 validated core loops, market-only features, and three outcomes: survival_60d, top-quartile quality, top-quartile traction_90d. Prefer interpretable models first.

## 16. Negative filters

The system may gain more value from recognizing bad conditions than perfectly identifying winners. Validate every skip rule historically.
