# Own-Game Calibration Loop

Third-party competitor data is most useful before we have our own portfolio. After several releases, our own data becomes the strongest calibration source because it measures our actual execution, development cost, Yandex performance, and economics.

## Freeze prediction before development

Before development starts, persist an immutable prediction/dossier snapshot containing:

```text
candidate concept version
decision version + validation status
market prior category/evidence
production assessment
expected risks
BUILD rationale
predicted development range
expected monetization pattern
```

Do not rewrite this snapshot after development starts.

## Capture actual production

Store where available:

```text
actual focused person-days/hours
asset/content work
QA/rework
scope cuts
major deviations
unexpected technical complexity
```

## Capture release outcome

Store actual metrics supported by our own Yandex analytics and economics:

```text
moderation outcome/time to publish
traffic/DAU
sessions/session duration
retention
gqRating/ratingCount
ad/economic metrics
ARPDAU/revenue
update cadence
```

## Early qualitative calibration

While Market Prior remains qualitative/ordinal, do not claim a numeric `prediction error` that the model did not actually output.

Store instead:

```text
predicted ordinal market-prior category
realized outcome cohort
production estimate vs actual
thesis falsified/supported/mixed
```

## Later numeric calibration

If a backtest-validated numeric ranking/probability model is introduced, then compute appropriate ranking/probability calibration error using the exact frozen model/version.

## Periodic calibration review

Every release appends evidence. It does **not** silently mutate thresholds/models.

Periodically review accumulated releases and, if justified, create new explicit versions of:

```text
Production Assessment rubrics
Decision Policy thresholds
Discovery heuristics
market-prior model/calibration
```

Old prediction snapshots and policy versions remain immutable.

## Developer-specific learning

Over time learn which patterns are specific to our actual workflow:

```text
which gameplay archetypes we implement best
which scopes we systematically underestimate
which asset/content patterns create delays
which monetization patterns work for us
which market priors translate into Yandex outcomes for our execution quality
```

This loop should gradually reduce dependence on imperfect competitor proxies rather than pretending those proxies can ever reveal every private competitor metric.
