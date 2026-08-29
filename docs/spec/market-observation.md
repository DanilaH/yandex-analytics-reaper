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

The exact implementation mechanics for creating/reusing these profiles are a separate Phase 2 task. Persisting the declared `session_profile` on a context does not by itself prove that the collector has implemented those semantics correctly.

## Probe run grouping

A paginated feed/search observation is one logical run, not unrelated page snapshots.

```text
ProbeContext
↓
ProbeRun
├── ProbePage 0 → raw snapshot
│      ↓ response continuation tokens
├── ProbePage 1 → raw snapshot
│      ↓ response continuation tokens
└── ProbePage N → raw snapshot
```

A run records the source/request surface, deterministic context identity, optional search query, requested page limit, start/completion times, status, and terminal error provenance.

Run status semantics:

```text
RUNNING
→ collection has started and no terminal state has been persisted

COMPLETED
→ at least one page exists and the run reached the requested page limit
   OR the source reported no next page

PARTIAL
→ at least one valid page was persisted, but the requested observation could not complete

FAILED
→ the run failed before any valid page was persisted
```

`COMPLETED` is relative to requested observation depth. For example, a one-page probe may be complete even when page 0 reports that deeper pages exist.

Each page stores:

```text
run_id
page_index
raw_snapshot_id
retrieved_at
request_page_id
request_rtx_reqid
response_next_page_id
response_rtx_reqid
has_next_page
```

Pages are contiguous (`0,1,2,...`) and retrieval time cannot move backwards. Page 0 cannot carry request continuation tokens. Every later page must consume exactly the continuation tokens emitted by the preceding page. If the source says `has_next_page=true` but omits a required continuation token, the current valid page remains persisted and the run becomes `PARTIAL`; no fabricated next page is appended.

A raw snapshot may belong to at most one probe page within the same source. Raw identity is `(source_id, raw_snapshot_id)`, not a globally unique snapshot ID detached from source identity.

If an HTTP/schema/parser/continuation failure occurs after a response was persisted, `error_raw_snapshot_id` points to the raw response that caused the terminal condition. If failure happens before any response exists, it remains null.

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
