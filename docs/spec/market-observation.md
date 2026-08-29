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
session_instance_id
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
→ session_instance_id = null
→ cookie_state_hash = null
→ profile_age_days = 0

persistent_anonymous
→ one explicit local anonymous profile is loaded before the run
→ its cookie jar is reused and updated across runs
→ session_instance_id = stable non-secret ID for that local persistent profile instance
→ cookie_state_hash = SHA-256 fingerprint of the cookie state loaded at run start
→ profile_age_days = whole days since that local profile was created

authenticated_test
→ reserved for an explicit controlled credential/profile provider
→ current default collector fails closed because no such provider is configured
→ it must never silently fall back to anonymous behavior
```

The persistent anonymous cookie jar is local runtime state, not market evidence. Raw cookie values may exist only in the local session-state file needed to reproduce the anonymous profile. They must never be copied into raw-snapshot request metadata, SQLite probe context, logs, or analytical tables.

`session_instance_id` is a randomly generated non-secret cohort identifier. It identifies one local persistent profile instance without identifying a Yandex user or exposing cookie material. Cookie churn does not change it. An explicit profile reset creates a new instance ID, so runs before and after the reset cannot be silently treated as the same persistent cohort. Legacy local persistent metadata created before this field existed is assigned an instance ID on its first successful open/save under the new format.

`cookie_state_hash` is provenance for distinguishing anonymous states; it is not an authentication token and must never be used to reconstruct cookie values. The fingerprint describes the state **loaded at the start of the run**. Cookies learned during the run are persisted locally for the next persistent run, so the next run receives the next fingerprint.

`session_instance_id`, `cookie_state_hash`, and `profile_age_days` participate in `ProbeContext` identity because they describe the actual observation state. For schema-drift comparison, cookie hash and profile age are intentionally excluded so normal cookie churn does not fragment schema baselines. `session_profile` and the stable `session_instance_id` remain comparison boundaries; an explicit persistent-profile reset therefore starts a fresh schema baseline rather than silently joining the old cohort.

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
session_instance_id = null
requested page size = 20
candidate maximum depths = 1 / 3 / 5 / 10
```

Each eligible trial is one run requested at up to 10 pages. The candidate depths are derived from prefixes of that same run, so depth is not confounded with four separately randomized/time-shifted collections. Legitimate source exhaustion before page 10 remains valid and saturates deeper candidate prefixes at the final available page.

Only organic cards participate in the depth decision. The analyzer replays immutable raw bodies, verifies their content hashes and stored `ProbePage` linkage, and rejects ineligible/corrupt trials rather than coercing them.

The v1 decision thresholds and minimum sample requirements are declared in `feed-depth-experiment.md` and must not be changed after viewing the first empirical result. The roadmap item remains incomplete until enough real eligible trials exist and the frozen rule yields a recommendation.

Session-profile stability, device/language variance, and collection cadence are separate experiments/tasks. Do not silently fold those dimensions into feed-depth-v1.

## Collection cadence

The first cadence decision is governed by the frozen `collection-cadence-v1` protocol in `collection-cadence-experiment.md`.

Daily observations are a finite-resolution **reference series**, not ground truth and not an event log. V1 therefore does not infer an exact source event rate. It retrospectively downsamples the same daily reference window at fixed candidates:

```text
1 / 2 / 3 / 7 days
```

Predeclaration and evidence binding are deliberately separate. Before day 1, an immutable SQLite cadence plan freezes the listing cohort, exact persisted query-family version, and 28+ planned checkpoint timestamps. Its `frozen_at` comes from the SQLite UTC clock and must be at least two hours before the first checkpoint. Future ProbeRun IDs are **not** part of that plan because they do not exist yet.

After collection, a separate evidence manifest binds actual daily feed/search run IDs to the stored `plan_id`. The submitted checkpoint timestamps must exactly match the frozen plan schedule; the late manifest cannot override the cohort, query family, freeze time, or reference window.

A valid window uses consecutive UTC dates, neighboring checkpoints 22–26 elapsed hours apart, one two-hour UTC clock-time band, and observation/run timing inside each checkpoint's two-hour eligibility window.

Cadence is chosen separately for:

```text
catalogue_metadata
game_page
recommendation_feed at depths 1 / 3 / 5 / 10
search at depths 1 / 3 / 5 / 10 across the frozen query family
```

Normalized state points retain exact observation IDs, field lineage, and raw snapshot IDs. Feed/search rankings are rebuilt by replaying immutable raw bodies and verifying persisted `ProbePage` linkage. Sponsored cards do not participate in ranking cadence metrics.

`event-driven` is not a v1 candidate because no proven Yandex push/subscription capability currently replaces polling. It must not be selected from snapshot volatility alone.

The empirical cadence result is still pending. Until the required real daily window is complete, no production cadence/default may be inferred from synthetic tests or the protocol thresholds.

## Search discovery and competitor sets

`totalGamesCount` remains a per-search supply signal. Do not sum it across variants and call the result a competitor count.

Search intent definitions use the immutable/versioned query-family semantics in `search-query-family.md`. The first comparable-set construction is frozen separately in `comparable-set.md`:

```text
exact persisted QueryFamilyVersion
→ exactly one explicit completed clean search ProbeRun per member
→ raw request/body replay with exact query/context/page linkage
→ parsed organic result union
→ dedupe by yandex_games:<appID>
→ immutable yandex_search_union_v1 comparable-set version + evidence
```

Query/run association is derived from exact persisted `query_text`, not caller order or fuzzy matching. All runs in `yandex_search_union_v1` share one exact `ProbeContext` and requested page limit. The current construction uses `clean_anonymous`; it does not consume the still-pending empirical session-profile result.

The union order is deterministic provenance order, not a relevance score: query-family ordinal → page index → parsed card order. Repeated organic listings add evidence but do not duplicate members. Sponsored cards do not contribute membership.

The current set is explicitly a **provisional search-derived candidate peer set**. Phase 3 taxonomy is still draft, so this construction does not auto-filter with the unvalidated classifier and does not claim every member is a confirmed gameplay comparable. Later taxonomy-refined construction must create a new version/method rather than rewrite historical search-union sets.

The parser owns the card representation available to this construction. `yandex_search_union_v1` uses `YandexFeedParser@2`; raw snapshots remain immutable so a later parser/construction version can revisit source details without rewriting v1 evidence.

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
