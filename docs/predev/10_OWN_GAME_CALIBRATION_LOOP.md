# Own-Game Calibration Loop

## 1. Long-term principle

Third-party competitor data is useful before we have our own portfolio. After several releases, our own data becomes the highest-value calibration source because it measures our execution quality, actual development cost, moderation experience, Yandex distribution, retention, and economics.

## 2. Freeze a prediction before development

Before starting a game, store an immutable prediction snapshot: candidate dossier version, market prior, production assessment, expected risks, BUILD rationale, predicted dev days, and expected monetization pattern. Do not edit it after development starts.

## 3. Capture actual development

Store actual dev days/hours where available, asset work, QA/rework, major deviations, scope cuts, and unexpected complexity.

## 4. Capture launch outcome

Capture moderation outcome/time to publish, initial traffic, DAU, sessions/session duration, retention, gqRating, ratingCount, ad metrics, ARPDAU, revenue, and update cadence.

## 5. Compare prediction vs reality

Calculate market-prior calibration error, production-cost error, traffic expectation error, and monetization expectation error.

## 6. Learn developer-specific priors

After enough games, learn which mechanics we implement best, which scopes we underestimate, which art/content burdens cause delays, which monetization patterns work for us, and which Yandex cohorts convert into revenue for us.

## 7. Portfolio feedback

Every release should update Production Assessment calibration, Market Prior calibration, Decision Policy thresholds, and Discovery heuristics. Do not automatically retrain/change thresholds from one outlier release.
