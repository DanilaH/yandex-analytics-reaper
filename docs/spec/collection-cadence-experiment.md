# Collection Cadence Calibration

Phase 2 must choose collection cadence from observed volatility rather than intuition. `collection-cadence-v1` treats **daily collection as a finite-resolution calibration reference**, then asks how much information would become stale if that reference were deterministically downsampled to slower schedules.

This is an operational sampling policy. It is not an event log and does not claim that a daily snapshot observes every source event between collections.

## Version identity

```text
spec_version = collection-cadence-v1
analyzer_version = 1
source = yandex_public
reference_cadence = daily
candidate_intervals_days = 1 / 2 / 3 / 7
minimum_reference_days = 28 consecutive UTC dates
minimum_listing_cohort = 20
metric normalizer = YandexGameNormalizer@2
listing-history normalizer = YandexListingHistoryNormalizer@1
feed/search ranking parser = YandexFeedParser@2
```

Candidate intervals, thresholds, cohort rules, and replay semantics are frozen before empirical calibration results are inspected. Changing them after seeing the first real report requires a new spec/analyzer version.

## Why downsampling instead of event-rate inference

Snapshot observations do not reveal every event between snapshots. If `ratingCount` is 100 on Monday and 110 on Tuesday, the evidence proves only that the observed state changed between those checkpoints. It does not prove the exact event count or timestamps.

V1 therefore evaluates slower schedules against the observed daily reference:

```text
daily reference checkpoints
→ retain only checkpoints available under candidate cadence
→ carry the last retained state/ranking forward
→ compare carried value with each daily reference checkpoint
→ quantify stale-state / ranking divergence
```

Reports must call this a daily reference, not ground truth.

## Two-stage empirical contract

A real calibration has two distinct persisted artifacts. This split is mandatory because future run IDs cannot be known before collection begins.

### Stage 1 — immutable plan before day 1

Before the first eligible checkpoint, persist a `CollectionCadencePlanDeclaration` containing only facts that can genuinely be predeclared:

```text
spec_version
plan_id
exact listing_ids cohort
query_family_id / query_family_version
28+ planned checkpoint_at timestamps
```

The plan deliberately does **not** contain:

```text
frozen_at supplied by the caller
future feed_run_id values
future search_run_ids values
empirical measurements
```

`freeze-collection-cadence-plan` persists the declaration into the operational SQLite store. `frozen_at` is assigned from the SQLite UTC clock at insertion time rather than trusted from JSON. The freeze must happen at least two hours before the first planned checkpoint.

The persisted plan is immutable by `plan_id`. Repeating identical content is idempotent while conflicting content under the same `plan_id` is rejected. The store also records a deterministic SHA-256 content hash over the declared cohort, query-family identity, and checkpoint schedule.

At freeze time:

- the exact persisted query-family version must already exist;
- the query family must belong to `yandex_public`;
- every listing cohort member must already exist in normalized identity storage;
- query-family `created_at` and listing `first_seen_at` must not be later than the actual freeze time.

This makes post-hoc cohort/window selection materially harder than a user-editable `frozen_at` field. The threat model does not attempt to defend against deliberate host/SQLite clock tampering.

### Stage 2 — evidence bindings after collection

After daily collection, a `CollectionCadenceManifest` contains only:

```text
spec_version
plan_id
checkpoints
  checkpoint_at
  exact feed_run_id
  exact search_run_ids
```

The analyzer loads cohort/query-family/schedule/freeze time from the immutable stored plan. It rejects the evidence manifest unless its ordered `checkpoint_at` values exactly equal the frozen plan schedule.

The late evidence file cannot override `frozen_at`, listing membership, query-family identity/version, or planned dates. Probe run IDs must be globally unique across submitted checkpoints.

The report records both the immutable `plan_hash` and deterministic evidence `manifest_id`.

## Capability-specific cadence

Do not force one global cadence across unrelated surfaces. V1 reports separately for:

```text
catalogue_metadata
game_page
recommendation_feed
search
```

Signal ownership:

```text
catalogue_metadata
→ yandex_games_rating
→ rating_count
→ media manifest hash

game_page
→ appVersion
→ source_published_at

recommendation_feed
→ organic ranking prefixes at depths 1 / 3 / 5 / 10

search
→ exact query-family member organic ranking prefixes at depths 1 / 3 / 5 / 10
```

Direct `published` presence may be collected as a by-product but V1 does not infer negative availability from result omission.

## Calibration cohort

### Listing cohort

The metadata/page cohort is frozen in the stage-1 plan before collection begins.

Minimum:

```text
20 distinct persisted Yandex listing IDs
```

The same cohort is used for the full window. Missing eligible observations make the affected series ineligible; the analyzer does not substitute a more convenient listing after seeing volatility.

Manual `probe-games` / `probe-page` remain raw-first. After successful raw persistence plus schema/parser validation they persist normalized identity, metric, and history evidence into the same SQLite operational store. This is calibration plumbing, not a production scheduler.

### Feed cohort

For every planned reference date, collect one completed recommendation-feed run with:

```text
source = yandex_public
request_key = catalogue.feed
kind = recommendation_feed
language = ru
device = desktop
platform = desktop_other
session_profile = clean_anonymous
requested page size = 20
requested maximum pages = 10
```

Legitimate source exhaustion before page 10 remains eligible. Candidate depths `1 / 3 / 5 / 10` are prefixes of the same run, saturating after legitimate exhaustion.

Cadence calibration does not consume the pending feed-depth or session-profile empirical conclusions. It reports every depth under the frozen clean-anonymous calibration context. Production feed cadence must later use only the depth/profile actually authorized by those separate empirical tasks.

### Search cohort

Search cadence uses the exact `QueryFamilyVersion` frozen into the plan. Every daily checkpoint requires one completed clean-anonymous search run for every exact family member under one shared context and requested page limit of 10.

Query/run association is exact by persisted `query_text`; fuzzy matching and caller-order inference are forbidden. Candidate depths `1 / 3 / 5 / 10` are derived from the same run prefixes and saturate after legitimate source exhaustion.

Search rankings remain separate per exact query member during measurement, but V1 emits one operational recommendation **per depth across the full frozen query family**, not a separate scheduler cadence for every query string.

## Daily reference schedule

The frozen plan requires at least 28 consecutive UTC dates.

Planned checkpoints must:

```text
be strictly increasing
have exactly one checkpoint per UTC date
use consecutive UTC dates
be spaced 22 to 26 elapsed hours apart
fit inside one circular two-hour UTC clock-time band
```

The elapsed-time guard prevents pathological sequences that merely cross UTC midnight while being one hour apart and then almost 47 hours apart. The clock band limits time-of-day confounding; neither rule claims the source has no intraday seasonality.

For normalized listing state, the selected observation is the latest eligible observation at or before the checkpoint with:

```text
0 <= checkpoint_at - observed_at <= 2 hours
retrieved_at <= checkpoint_at
```

Older evidence is missing daily-reference coverage. It is not carried into the reference series. Carry-forward occurs only inside candidate downsampling after the daily reference is constructed.

Feed/search runs must start within two hours before their bound checkpoint and complete no later than that checkpoint.

## State-series construction

V1 uses exact canonical state equality rather than tuning numerical tolerances after seeing results.

Per listing:

```text
catalogue metric series
→ yandex_games_rating
→ rating_count

catalogue media series
→ manifest_hash when media evidence exists

game-page update series
→ canonical tuple(app_version, source_published_at)
```

A missing observation is coverage failure, not a synthetic `None` state. Numeric canonicalization preserves integer identity instead of converting every number through binary float.

The operational question is deliberately strict: would the slower schedule reproduce the state observed by the daily reference?

## State provenance

Every eligible normalized state point must retain:

```text
exact normalized observation_id
field-level lineage
raw snapshot ID(s)
raw body/hash replayability
normalizer name/version
retrieved_at agreement with raw metadata
```

The report records exact observation IDs and raw snapshot IDs for every eligible state checkpoint. Later backfill cannot silently change which evidence the saved report depended on. Corrupt or missing provenance fails closed and rejects the affected series.

## Ranking-series construction

Feed/search rankings use the first organic occurrence of each listing. Sponsored cards are excluded.

For each checkpoint and depth:

```text
ordered unique organic listing IDs
```

A ranking must contain at least one organic result. Feed/search raw bodies are replayed and must reconstruct the persisted `ProbePage` request/context/pagination chain exactly.

## Candidate downsampling

Candidate intervals:

```text
1 day   = daily
2 days  = every other reference checkpoint
3 days  = every third reference checkpoint
7 days  = weekly
```

For candidate interval `N`, retained indices are:

```text
0, N, 2N, 3N, ...
```

At each daily reference index, the simulated slower collector knows only the most recent retained checkpoint at or before that index. These are retrospective deterministic downsamplings of one reference window, not independently recollected N-day experiments.

## State metrics

For each state series and interval:

```text
reference_match_ratio =
  count(carried_state == daily_reference_state) / reference_checkpoint_count
```

Aggregate:

```text
median reference_match_ratio
p25 reference_match_ratio
minimum reference_match_ratio   diagnostic
series count
```

Percentiles use linear interpolation at `(n - 1) * p`.

## Ranking metrics

At every daily checkpoint compare carried and reference rankings using:

```text
Jaccard set similarity
ranked-prefix overlap with persistence p = 0.90
```

For each ranking series/interval calculate median daily Jaccard and ranked overlap, then aggregate across eligible series for the capability/depth:

```text
median series-median Jaccard
p25 series-median Jaccard
median series-median ranked overlap
p25 series-median ranked overlap
```

## Frozen operational tolerances

These are product/operations tolerances, not statistical confidence levels.

State passes only if:

```text
median reference_match_ratio >= 0.90
p25 reference_match_ratio >= 0.80
```

Ranking capability/depth passes only if:

```text
median series-median Jaccard >= 0.80
p25 series-median Jaccard >= 0.65
median series-median ranked overlap >= 0.75
p25 series-median ranked overlap >= 0.60
```

Daily must be an exact identity comparison. For every capability/depth, recommend the **slowest** candidate interval that passes.

Catalogue metadata requires both `yandex_games_rating` and `rating_count`. A complete 20+ series media cohort also participates; otherwise media remains diagnostic-only.

## Minimum empirical coverage

No recommendation is emitted without a complete daily reference window for the affected series.

```text
catalogue_metadata
→ at least 20 complete yandex_games_rating series
→ at least 20 complete rating_count series
→ media participates only with at least 20 complete series

game_page
→ at least 20 complete update-state series

recommendation_feed
→ every planned date has one eligible daily feed run

search
→ every frozen query-family member has one eligible daily search run per planned date
```

A capability that fails its gate reports `recommended_interval_days = null`. It cannot borrow another capability's cadence.

## Decision interpretation

Example shape only:

```text
catalogue_metadata → 1 day
game_page          → 7 days
feed depth 1       → 1 day
feed depth 3       → 1 day
feed depth 5       → 2 days
feed depth 10      → 2 days
search depth 1     → 1 day across frozen query family
search depth 3     → 3 days across frozen query family
```

Actual values must come from real empirical evidence. This specification selects none of them.

## Event-driven collection

`event-driven` is not a V1 candidate because the current Yandex capability set has no proven event/subscription surface replacing polling. A future notification capability requires its own evidence and policy version.

## Report requirements

A report records at minimum:

```text
spec/analyzer version
plan_id + immutable plan_hash + database frozen_at
deterministic evidence manifest_id
frozen listing cohort
query-family identity/version
exact planned checkpoints
exact submitted feed/search run IDs
exact normalized observation IDs + raw snapshot IDs for eligible state points
eligible/rejected series with reasons
reference coverage
per-candidate diagnostics/aggregates
per-capability/depth recommendation or null
frozen decision policy
```

Synthetic fixtures validate mechanics only. They are never the empirical cadence result.

## CLI workflow

Before day 1, after listing identities/query family exist:

```text
yandex-reaper freeze-collection-cadence-plan cadence-plan.json --output data/raw
```

The plan JSON contains cohort/query-family/planned checkpoint timestamps only. The command prints the immutable stored plan including DB-generated `frozen_at` and `content_hash`.

Collect daily evidence and record the resulting run IDs. After the planned window, create an evidence-binding JSON containing the stored `plan_id` and exact run IDs for each frozen checkpoint, then run:

```text
yandex-reaper analyze-collection-cadence cadence-evidence.json --output data/raw
```

The operational SQLite database is resolved next to the selected raw root. Analysis must not silently create a new empty evidence database.

## Non-goals

V1 does not:

- claim the daily reference captures every source event;
- infer exact change timestamps or event rates between snapshots;
- accept a caller-supplied/backdated `frozen_at` as predeclaration evidence;
- require future run IDs to be known before collection;
- consume pending feed-depth/session-profile empirical results;
- change listing/query-family membership after seeing churn;
- infer negative listing status from one omitted result;
- invent source push/event support;
- schedule production collection before the empirical report exists;
- choose one global cadence for every source capability;
- create per-query production schedules inside the frozen search family.
