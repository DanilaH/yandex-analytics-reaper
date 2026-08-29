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

The persisted `ProbeContext` is the **effective context actually opened by the session manager**, not merely the user's requested label.

```text
clean_anonymous
→ a fresh HTTP client and cookie jar for every logical probe run
→ no auth
→ no cookie/profile state reused from an earlier run
→ cookie_state_hash = null
→ profile_age_days = 0

persistent_anonymous
→ one explicit local anonymous profile is loaded before the run
→ its cookie jar is reused and updated across runs
→ cookie_state_hash = SHA-256 fingerprint of the cookie state loaded at run start
→ profile_age_days = whole days since that local profile was created

authenticated_test
→ reserved for an explicit controlled credential/profile provider
→ current default collector fails closed because no such provider is configured
→ it must never silently fall back to anonymous behavior
```

The persistent anonymous cookie jar is local runtime state, not market evidence. Raw cookie values may exist only in the local session-state file needed to reproduce the anonymous profile. They must never be copied into raw-snapshot request metadata, SQLite probe context, logs, or analytical tables.

`cookie_state_hash` is provenance for distinguishing anonymous states; it is not an authentication token and must never be used to reconstruct cookie values. The fingerprint describes the state **loaded at the start of the run**. Cookies learned during the run are persisted locally for the next persistent run, so the next run receives the next fingerprint.

`cookie_state_hash` and `profile_age_days` participate in `ProbeContext` identity because they describe the actual observation state, but they are intentionally excluded from schema-drift comparison scope so normal cookie churn does not fragment schema baselines. `session_profile` remains part of schema scope because anonymous vs future authenticated surfaces may legitimately differ in shape. This scope-semantics change requires a new schema-analyzer version.

Persistent state is saved when the prepared session closes, including after a partial/failed probe when possible. A local state-save failure must not replace the original collection/parser failure; the original error remains primary and the state error is attached as secondary diagnostic context.

If the persistent profile is incomplete, corrupt, or has impossible time metadata, collection fails closed. Do not silently reset it and call the resulting observation the same persistent cohort.

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

The first feed-depth decision is governed by the frozen `feed-depth-v1` protocol in `feed-depth-experiment.md`.

Its scope is intentionally narrow:

```text
recommendation feed
ru
desktop / desktop_other
clean_anonymous
requested page size = 20
candidate maximum depths = 1 / 3 / 5 / 10
```

Each eligible trial is one run requested at up to 10 pages. The candidate depths are derived from prefixes of that same run, so depth is not confounded with four separately randomized/time-shifted collections. Legitimate source exhaustion before page 10 remains valid and saturates deeper candidate prefixes at the final available page.

Only organic cards participate in the depth decision. The analyzer replays immutable raw bodies, verifies their content hashes and stored `ProbePage` linkage, and rejects ineligible/corrupt trials rather than coercing them.

The v1 decision thresholds and minimum sample requirements are declared in `feed-depth-experiment.md` and must not be changed after viewing the first empirical result. The roadmap item remains incomplete until enough real eligible trials exist and the frozen rule yields a recommendation.

Session-profile stability, device/language variance, and collection cadence are separate experiments/tasks. Do not silently fold those dimensions into feed-depth-v1.

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
