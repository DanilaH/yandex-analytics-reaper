# Probe & Market-State Policy v2

## 1. Core principle

A feed/search observation is not "the market". It is:

```text
surface × context × time × session profile
```

## 2. Observation context

Store observed_at, language, device type, platform, country observed, collector region, authenticated state, session profile, cookie-state hash, profile age, request parameters, and response request ID.

Session profiles:

```text
clean_anonymous
persistent_anonymous
authenticated_test
```

Never store raw authentication cookies/tokens in snapshot metadata.

## 3. Global metric vs contextual exposure

Do not duplicate every game metric per context unless empirical evidence shows it varies.

Separate `GameMetricObservation` from `ContextualExposureObservation`.

Examples: gqRating/ratingCount are game metrics unless proven context-dependent; feed/search positions are contextual exposure.

## 4. Feed semantics

Store surface type (`recommendation_feed`, `new`, `popular`, `category`, `search`) and exposure type (`organic`, `sponsored`, `editorial`, `unknown`).

`Popular` must not be modeled as pure organic recommendation performance because platform selection may be editorial/manual.

## 5. Do not hardcode first 3 pages forever

Run a stability experiment comparing depths 1/3/5/10 pages across repeated sessions/times. Measure Jaccard overlap, marginal unique-game gain, rank correlation, first-page stability, time-of-day variance, and device/language variance. Choose the smallest useful depth.

## 6. Probe frequency must be measured

Start daily during calibration, then measure gqRating changes, rating-count velocity, feed/search churn, and update frequency. Choose daily/3x-weekly/weekly/event-driven cadence from observed volatility.

## 7. Search is discovery, not canonical competition

Correct pipeline:

```text
query family
→ variants/synonyms
→ union result appIDs
→ dedupe
→ taxonomy classification
→ comparable-game set
→ competitor metrics
```

`totalGamesCount` is a separate search-supply signal, not competitor count.

## 8. Candidate search families

For every active candidate store canonical concept, query families, theme aliases, mechanic aliases, language, and query version.

## 9. Sponsored/exposure handling

Observed sponsored indicators include `source`, `click_link`, and `badgeType == badge.direct`. Sponsored exposure is never evidence of organic recommendation strength.

## 10. Deletion/unavailability

Disappearance from a feed is not deletion. Direct listing status supports published, temporarily unavailable, unpublished, deleted, and unknown. If cause is unknown, keep it unknown.
