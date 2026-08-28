# Market Observation Policy

A feed/search observation is not "the market". It is:

```text
surface × context × session profile × probe run × time
```

## Observation context

Store:

```text
language
device_type
platform
country_observed
collector_region
session_profile
cookie_state_hash
profile_age
request parameters
```

`session_profile` is the source of truth for auth/session behavior; do not duplicate it with an independently mutable boolean auth flag.

### Session-profile semantics

```text
clean_anonymous
→ new cookie jar/profile state for the probe run; no auth; no persisted recommendation history reused

persistent_anonymous
→ stable anonymous profile/cookie state intentionally reused across runs

authenticated_test
→ explicit test account/profile; behavior must be kept separate from anonymous cohorts
```

Never persist raw auth cookies/tokens in snapshot metadata.

## Probe run grouping

A paginated observation is one logical run, not unrelated page snapshots.

```text
probe_run
  id
  surface
  context
  started_at
  completed_at
  coverage_status

probe_page
  probe_run_id
  page_number
  raw_snapshot_id
  next_page_id
  response_request_id
```

This allows a five-page feed crawl to be reconstructed as one sampled observation.

## Game metrics vs contextual exposure

Keep separate:

```text
GameMetricObservation
ContextualExposureObservation
```

Examples:

```text
gqRating/ratingCount
→ game metric unless empirical evidence proves context variance

feed/search position
→ contextual exposure
```

## Surface/exposure semantics

Surface examples:

```text
recommendation_feed
new
popular
category
search
```

Exposure selection origin:

```text
organic
sponsored
editorial
unknown
```

`Popular` is not assumed to be pure algorithmic recommendation evidence. Sponsored exposure is never used as organic recommendation strength.

## Feed-depth calibration

Do not hardcode three pages forever.

Initial experiment compares:

```text
1 / 3 / 5 / 10 pages
```

across repeated times/session profiles and measures:

```text
Jaccard overlap
unique organic-game marginal gain
rank stability/correlation
first-page stability
time-of-day variance
device/language variance
```

The experiment must declare a decision rule **before** reading the final result. Example structure:

```text
choose the smallest depth N where
marginal unique organic-game gain from deeper sampling is below a declared threshold
AND
top-ranked exposure stability no longer changes materially
```

Exact thresholds are part of the experiment spec, not chosen after looking at the outcome.

## Collection cadence

Start with daily calibration observations, measure volatility, then choose cadence based on evidence:

```text
gqRating/ratingCount change rate
feed/search churn
version/update frequency
```

Possible cadence: daily, several times/week, weekly, or event-driven.

## Search discovery and competitor sets

`totalGamesCount` remains a search-supply signal.

Comparable-game construction uses:

```text
versioned query family
→ synonyms/variants
→ result union
→ dedupe listing IDs
→ taxonomy filtering/similarity
→ versioned comparable set
```

Store the query-family version and exact comparable-set membership for reproducibility.

## Listing availability

Disappearance from a feed does not mean deletion.

Status can include:

```text
published
temporarily_unavailable
unpublished
deleted
unknown
```

Unknown cause remains unknown.
