# Collection Cadence Calibration

Phase 2 must choose collection cadence from observed volatility rather than from intuition. `collection-cadence-v1` treats **daily collection as a calibration reference**, then asks how much information would become stale if that daily reference series were downsampled to slower candidate cadences.

This is an operational sampling policy, not a claim that a daily snapshot observes every source event between collections.

## Version identity

```text
spec_version = collection-cadence-v1
analyzer_version = 1
source = yandex_public
reference_cadence = daily
candidate_intervals_days = 1 / 2 / 3 / 7
minimum_reference_days = 28 consecutive UTC dates
metric normalizer = YandexGameNormalizer@2
listing-history normalizer = YandexListingHistoryNormalizer@1
feed/search ranking parser = YandexFeedParser@2
```

The thresholds and candidate intervals in this document are frozen before empirical calibration results are inspected. Changing them after seeing the first real report requires a new spec/analyzer version.

## Why downsampling instead of event-rate inference

Snapshot observations do not reveal every event that happened between snapshots. If `ratingCount` is 100 on Monday and 110 on Tuesday, the data proves only that the observed state changed between those observations; it does not prove one event, ten events, or their exact timestamps.

Therefore v1 does **not** estimate a Poisson event rate or pretend to know exact update frequency. It evaluates a slower schedule against the actual daily reference states that were observed:

```text
daily reference checkpoints
→ retain only checkpoints available under candidate cadence
→ carry the last retained observation forward
→ compare that carried state/ranking with each daily reference checkpoint
→ quantify stale-state / ranking divergence
```

The daily reference is still an observation process with finite resolution. Reports must call it a reference, not ground truth.

## Capability-specific cadence

Do not force one global cadence across unrelated source surfaces. v1 reports separate recommendations for:

```text
catalogue_metadata
game_page
recommendation_feed
search
```

Current signal ownership:

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

Direct `published` presence status is collected as a by-product of successful metadata/page observations. v1 does not use absence of a negative status as evidence that availability is unchanged.

## Frozen experiment manifest

A real empirical run is driven by one explicit manifest containing:

```text
spec_version
frozen_at
exact listing_ids cohort
query_family_id / query_family_version
28+ daily checkpoints
  checkpoint_at
  exact feed_run_id
  exact search_run_ids
```

`frozen_at` must be no later than two hours before the first checkpoint. The persisted `QueryFamilyVersion.created_at` must be no later than `frozen_at`.

This prevents the analyzer from selecting a convenient query family after seeing the calibration data. The listing cohort is likewise declared in the manifest before collection. The recommended operating procedure is to commit/save that manifest before day 1; the timestamp is an analytical guard, not cryptographic proof that a file was not edited later.

The manifest receives a deterministic content hash in the report. Reusing a different manifest is therefore a different empirical input even if some run IDs overlap.

## Calibration cohort

### Listing cohort

The metadata/page calibration cohort is explicit and frozen before collection begins.

Minimum:

```text
20 distinct persisted Yandex listing IDs
```

The analyzer does not select convenient listings after seeing volatility. The same cohort is used for all reference dates. A listing without sufficient eligible observations makes its affected series ineligible; the report exposes missing coverage rather than silently substituting another listing.

The existing manual `probe-games` / `probe-page` commands remain raw-first. After successful raw persistence + schema/parser validation, they also persist normalized identity/metric/history evidence into the same operational SQLite store. This is calibration plumbing, not a production scheduler.

### Feed cohort

For each reference date, collect one completed recommendation-feed run with the frozen feed shape used by the existing experiments:

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

Legitimate source exhaustion before page 10 remains eligible. Candidate depths `1 / 3 / 5 / 10` are derived as prefixes of that same run, exactly as in the existing replay tooling.

This calibration does not consume the still-pending feed-depth or session-profile empirical conclusions. It reports every candidate depth under the frozen clean-anonymous calibration context. The eventual production feed cadence is selected at the depth/profile that later empirical tasks actually authorize.

### Search cohort

Search cadence uses one exact persisted `QueryFamilyVersion`. For every reference date there must be one completed clean-anonymous search run for every exact family member under one shared context and requested page limit of 10.

Query association is exact by persisted `query_text`; fuzzy matching and caller-order inference are forbidden. Candidate depths `1 / 3 / 5 / 10` are derived from the same run prefixes where available, saturating after legitimate source exhaustion.

Search ranking series remain separate per exact query member during replay/measurement, but the v1 operational recommendation is one cadence **per depth across the frozen query family**. V1 does not create a different scheduler cadence for every query string.

## Daily reference checkpoints

A v1 empirical report requires at least 28 consecutive UTC dates. Every capability checkpoint is bound to an explicit UTC `checkpoint_at` supplied in the experiment manifest.

Reference checkpoints must:

```text
use 28+ consecutive UTC dates
have strictly increasing checkpoint_at values
have exactly one checkpoint per UTC date
keep the UTC clock time inside one fixed two-hour band across the report
be spaced 22 to 26 elapsed hours apart
```

The clock-time band limits time-of-day confounding. The 22–26 hour elapsed-time guard prevents pathological sequences that technically use consecutive UTC dates but are only an hour apart around midnight and then almost 47 hours apart.

For listing state series, the observation used at a checkpoint is the latest eligible observation at or before `checkpoint_at`, with:

```text
0 <= checkpoint_at - observed_at <= 2 hours
retrieved_at <= checkpoint_at
```

An older observation is missing coverage; it is not carried into the **daily reference** series. Carry-forward happens only when simulating a slower candidate cadence after the daily reference series is constructed.

Feed/search runs bound to a checkpoint must start within two hours before `checkpoint_at` and must complete no later than `checkpoint_at`.

## State-series construction

V1 uses exact canonical state equality rather than inventing metric-specific numerical tolerances after seeing data.

Per listing:

```text
catalogue metric series
→ one series for yandex_games_rating
→ one series for rating_count

catalogue media series
→ manifest_hash when a media observation exists

game-page update series
→ canonical tuple(app_version, source_published_at)
```

A missing observation on a reference day is coverage failure, not a state value. `None` must not be inserted as if the source explicitly reported null.

Numeric canonicalization preserves integer identity rather than round-tripping every value through binary float. Exact equality intentionally asks a strict operational question: "would the slower schedule reproduce the state observed by the daily reference?"

Magnitude-of-change diagnostics may be added in a later analyzer version but must not retroactively alter the v1 decision rule.

## State provenance

Every eligible normalized state point must retain:

```text
exact normalized observation_id
field lineage
raw snapshot ID(s)
raw snapshot body/hash replayability
normalizer name/version
retrieved_at agreement with raw metadata
```

The empirical report records the exact observation ID and raw snapshot IDs used for every eligible state-series checkpoint. This prevents a later backfill with an older `observed_at` from silently changing what evidence the saved report depended on.

Storage corruption/missing provenance fails closed. An affected state series is rejected rather than coerced into a value.

## Ranking-series construction

Feed/search rankings contain first organic occurrence of each listing only. Sponsored cards are excluded from cadence ranking comparisons.

For each daily reference checkpoint and depth:

```text
ordered unique organic listing IDs
```

A ranking must contain at least one organic result. Shallower rankings must be prefixes of the replayed maximum-depth ranking, with legitimate source exhaustion saturating deeper candidates.

Feed and search ranking evidence is bound to the exact submitted probe-run IDs. Raw bodies are replayed and must reconstruct the persisted `ProbePage` chain exactly.

## Candidate downsampling

Candidate intervals:

```text
1 day   = daily
2 days  = every other reference checkpoint
3 days  = every third reference checkpoint
7 days  = weekly
```

For a candidate interval `N`, retained reference indices are:

```text
0, N, 2N, 3N, ...
```

At every daily reference index, the simulated slower collector knows only the most recent retained checkpoint at or before that index.

This is a deterministic retrospective downsample of the same reference series; it does not recollect independent N-day trials.

## State metrics

For each state series and candidate interval:

```text
reference_match_ratio =
  count(carried_state == daily_reference_state) / reference_checkpoint_count
```

Aggregate across eligible state series for one signal/capability:

```text
median reference_match_ratio
p25 reference_match_ratio
minimum reference_match_ratio          diagnostic
series count
```

Percentiles use linear interpolation at `(n - 1) * p`, consistent with existing experiment tooling.

## Ranking metrics

At each daily checkpoint compare the carried candidate ranking with the daily reference ranking using:

```text
Jaccard set similarity
ranked-prefix overlap with persistence p = 0.90
```

For every ranking series and candidate interval, calculate median daily Jaccard and median daily ranked-prefix overlap. Then aggregate across eligible ranking series for the capability/depth:

```text
median series-median Jaccard
p25 series-median Jaccard
median series-median ranked overlap
p25 series-median ranked overlap
```

`rank_persistence = 0.90` is frozen in v1.

## Predeclared operational tolerance

The following are **product/operations tolerances**, not statistical confidence levels.

A candidate cadence passes a state signal only if:

```text
median reference_match_ratio >= 0.90
p25 reference_match_ratio >= 0.80
```

A candidate cadence passes a ranking capability/depth only if all hold:

```text
median series-median Jaccard >= 0.80
p25 series-median Jaccard >= 0.65
median series-median ranked overlap >= 0.75
p25 series-median ranked overlap >= 0.60
```

Daily is the reference and therefore should be an identity comparison when the reference series is valid. If daily does not evaluate to exact identity, the analyzer/report is invalid.

For each capability/depth, recommend the **slowest** candidate interval that passes its frozen thresholds. Catalogue metadata must pass both required metric signals; a complete media cohort participates when at least 20 media series are eligible.

The thresholds express the project's willingness to trade collection cost for stale observations. They do not establish universal analytical best practice.

## Minimum empirical coverage

No cadence recommendation is emitted unless the affected capability has a complete daily reference window.

Additional minimums:

```text
catalogue_metadata
→ at least 20 rating_count state series
→ at least 20 yandex_games_rating state series
→ media series reported when complete; media is diagnostic if fewer than 20 complete series exist

game_page
→ at least 20 complete update-state series

recommendation_feed
→ one eligible ranking series per depth built from every daily feed run

search
→ one frozen query-family version
→ every family member has an eligible complete daily ranking series per depth
```

A capability that fails its coverage gate reports `recommended_interval_days = null`. It must not borrow another capability's cadence.

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

The actual values must come from the empirical report. This document does not preselect them.

For feed, the production schedule must later consult the empirically selected feed depth and authorized session-profile policy; v1 cadence tooling must not use unfinished experiment outcomes as assumptions.

## Event-driven collection

`event-driven` is not a candidate in v1 because the current Yandex capability set has no proven event/subscription surface that can replace polling. If a reliable source notification capability is discovered later, it requires its own evidence and policy version rather than being selected from snapshot volatility alone.

## Report requirements

A report records at minimum:

```text
spec/analyzer version
deterministic manifest_id
manifest frozen_at
frozen listing cohort
query-family identity/version
exact submitted checkpoints/feed/search run IDs
exact normalized observation IDs + raw snapshot IDs for eligible state points
eligible and rejected series with reasons
reference-date coverage
per-series diagnostics
per-candidate aggregate metrics
per-capability/depth recommendation or null
frozen decision policy
```

Synthetic fixtures validate analyzer mechanics only. They are never the empirical cadence result.

## CLI workflow

The analyzer consumes one JSON manifest:

```text
yandex-reaper analyze-collection-cadence cadence-manifest.json --output data/raw
```

The operational SQLite database is resolved next to the selected raw root, consistent with the other experiment tooling. The analyzer must not silently create a new empty database when empirical evidence is expected.

## Non-goals

V1 does not:

- claim the daily reference captures every source event;
- infer exact change timestamps between snapshots;
- consume pending feed-depth/session-profile empirical results;
- change listing/query-family membership after seeing churn;
- infer negative listing status from one omitted result;
- invent source push/event support;
- schedule production collection before the empirical report exists;
- choose one global cadence for every source capability;
- create per-query production schedules inside the frozen search family.
