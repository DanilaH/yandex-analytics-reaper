# Session-Profile Stability Experiment v1

This specification freezes the first Yandex recommendation-feed session-profile stability experiment **before** its outcome is inspected.

The goal is narrow: determine whether `clean_anonymous` and one controlled `persistent_anonymous` profile produce feed observations that differ materially beyond the feed's own short-window same-profile variability.

This experiment does **not** prove statistical equivalence, choose collection cadence, or decide search-session behavior. It is a controlled recommendation-feed calibration. The pending feed-depth calibration is not consumed here; the experiment reports profile effects independently at depths `1 / 3 / 5 / 10` so the eventual selected feed depth can use the corresponding result without retrofitting this protocol.

## Experiment identity

```text
spec_version = session-profile-stability-v1
analyzer_version = 1
feed_parser_version = 2
source_id = yandex_public
surface = recommendation_feed
candidate_depths = 1 / 3 / 5 / 10 pages
requested_page_limit = 10 pages
page_size = 20 requested cards
language = ru
device_type = desktop
platform = desktop_other
country_observed = null
collector_region = null
stable feed params = games_count=20, with_promos=false, lang=ru,
                     device-type=desktop, platform=desktop_other
only page_id / rtx-reqid may vary between pages
```

Each run is collected with an up-to-10-page maximum. Candidate depths are replay-derived prefixes of the same immutable run. Legitimate source exhaustion before page 10 saturates deeper candidate rankings at the final available organic ranking.

Only organic cards participate in stability metrics. Sponsored cards remain observable but never count as organic profile similarity.

## Matched-block design

One experimental block contains exactly four completed feed runs:

```text
2 × clean_anonymous
2 × persistent_anonymous
```

All four run starts must fall within a maximum 10-minute span. Their actual chronological order must be one of:

```text
C-P-P-C
P-C-C-P
```

where `C = clean_anonymous` and `P = persistent_anonymous`.

The mirrored order controls simple collection-order/time drift without pretending four requests are simultaneous. Run IDs are explicit block membership; the analyzer derives chronology from persisted `started_at`, not from caller-provided ordering.

Within a block:

- both clean runs must have `session_instance_id = null`, `cookie_state_hash = null`, `profile_age_days = 0`;
- both persistent runs must have the same non-null `session_instance_id`;
- persistent cookie fingerprints may differ because the profile evolves after each run;
- all persistent runs across the **entire experiment report** must belong to that same `session_instance_id`;
- all run IDs must be unique across all submitted blocks.

A reset to a different persistent session instance is a new cohort and must not be mixed into the same v1 report.

## Run eligibility

Every run in an eligible block must satisfy:

```text
source_id = yandex_public
probe_kind = recommendation_feed
request_key = catalogue.feed
status = completed
requested_page_limit = 10
persisted pages = contiguous prefix from page 0, with 1..10 pages total
if fewer than 10 pages exist, the final page reports source exhaustion
language = ru
device_type = desktop
platform = desktop_other
country_observed = null
collector_region = null
stable feed request params exactly match the frozen cohort
pagination request params match stored cursor linkage
all raw bodies still match persisted content hashes
all pages replay under YandexFeedParser@2
replayed raw request/context/response pagination reconstructs stored ProbePage exactly
at least one organic game exists in the replayed run
```

A corrupt/incomplete run rejects its block rather than being silently repaired. A `partial`/`failed` run is an operational failure, not evidence about session-profile stability.

If individually valid blocks contain more than one persistent `session_instance_id`, the submitted analysis is a cohort-definition error and must fail rather than choose a convenient instance.

## Minimum sample before conclusions

The report is `insufficient` and must not classify any depth until it contains at least:

```text
6 eligible matched blocks
4 hours between earliest and latest eligible block starts
3 distinct UTC hour buckets represented by eligible block starts
at least 2 eligible C-P-P-C blocks
at least 2 eligible P-C-C-P blocks
```

A block's time anchor is its earliest run `started_at`.

These are minimum anti-confounding guards for the first calibration, not a claim of formal statistical power.

## Per-block metrics

For each run and candidate depth `N`, construct the unique organic ranked list using each app ID's first organic occurrence up to depth `N`. If the source exhausted earlier, use the final available ranking.

For each block and depth compute ordinary set Jaccard and the same deterministic top-weighted ranked-prefix overlap used by `feed-depth-v1` (`p = 0.9`).

Let the two clean runs be `C1/C2` and the two persistent runs be `P1/P2` after classification by profile, independent of chronological position.

For each similarity metric `S`:

```text
within_clean_S      = S(C1, C2)
within_persistent_S = S(P1, P2)
within_baseline_S   = min(within_clean_S, within_persistent_S)

cross_profile_S
= median(
    S(C1, P1),
    S(C1, P2),
    S(C2, P1),
    S(C2, P2)
  )

profile_gap_S
= max(0, within_baseline_S - cross_profile_S)
```

Using the weaker of the two same-profile similarities is intentionally conservative: cross-profile similarity is not penalized for being lower than an unusually stable profile if it is still as reproducible as the noisier controlled profile.

Also report clean/persistent unique-organic counts as diagnostics, but do not add a post-hoc count threshold to the v1 decision.

## Ranked-prefix overlap

For ranked lists `A` and `B`, let `A_d` and `B_d` be the sets contained through rank `d` (or the complete list when it has already ended):

```text
X_d = |A_d ∩ B_d| / d
k = max(length(A), length(B))
p = 0.9

ranked_prefix_overlap
= Σ[d=1..k] ((1-p) * p^(d-1) * X_d)
  + p^k * X_k
```

The denominator remains `d` when one list has ended. Empty-vs-empty similarity is `1.0`; an eligible run itself must still contain at least one organic game at its full available depth.

## Aggregate metrics

At every candidate depth report across eligible blocks:

```text
median within-baseline Jaccard
median cross-profile Jaccard
median Jaccard profile gap
75th percentile Jaccard profile gap

median within-baseline ranked overlap
median cross-profile ranked overlap
median ranked-overlap profile gap
75th percentile ranked-overlap profile gap

median clean unique-organic count
median persistent unique-organic count
```

For the two count diagnostics, pool the two clean-run counts from every eligible block and take their median; independently pool the two persistent-run counts and take their median. The count diagnostics do not affect classification.

The 75th percentile uses deterministic linear interpolation: sort values, calculate `position = (n - 1) * 0.75`, and linearly interpolate between floor/ceiling positions.

## Predeclared per-depth classification

No depth receives a classification until the report-level minimum sample is sufficient.

For each depth, first require interpretable same-profile repeatability:

```text
median within-baseline Jaccard >= 0.50
AND
median within-baseline ranked overlap >= 0.50
```

If either baseline is below `0.50`, classify that depth as:

```text
inconclusive
```

because the feed is too unstable within controlled profiles to attribute a cross-profile difference confidently.

Otherwise classify the depth as `stable` only when **all** profile-effect guards hold:

```text
median Jaccard profile gap <= 0.10
75th percentile Jaccard profile gap <= 0.15
median ranked-overlap profile gap <= 0.10
75th percentile ranked-overlap profile gap <= 0.15
```

If the baseline is interpretable but any profile-effect guard fails, classify the depth as:

```text
material_difference
```

Interpretation:

- `stable` means no material session-profile effect was observed beyond same-profile short-window variability under these frozen tolerances; it is not proof that profiles are universally equivalent;
- `material_difference` means the clean↔persistent difference exceeds the declared tolerance and the profiles must not be collapsed at that depth without new evidence;
- `inconclusive` means same-profile feed instability is too high for the v1 design to attribute the difference;
- `insufficient` is report-level and means the minimum block/time/order sample has not been met.

The threshold values above must not change after viewing the first empirical result. Any later tolerance change requires a new spec version.

## Relationship to pending feed-depth calibration

This experiment intentionally produces a classification for **every** depth `1 / 3 / 5 / 10`. It must not select one of those depths or consume an unfinished feed-depth recommendation.

After `feed-depth-v1` eventually selects a default depth, downstream collection policy may consult the session-profile classification for that exact depth. Until then, no global "profiles are equivalent" or "profiles differ" claim may be inferred from a convenient depth.

## Output semantics

The report must include:

```text
spec_version
analyzer_version
feed parser version
submitted block run IDs
eligible block run IDs
rejected blocks + reasons
persistent session_instance_id or null
eligible block count
sample time span
represented UTC hour buckets
C-P-P-C / P-C-C-P block counts
sample_sufficient boolean
per-depth aggregate metrics + classification
decision reasons
```

Synthetic fixtures validate analyzer mechanics only; they are not empirical session-profile calibration evidence.
