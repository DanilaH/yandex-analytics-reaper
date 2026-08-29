# Feed-Depth Experiment v1

This specification freezes the first Yandex recommendation-feed depth experiment **before** its outcome is inspected.

The goal is narrow: choose the smallest default page depth that captures nearly all useful organic feed exposure without materially reducing reproducibility of the top-ranked exposure signal.

This experiment does **not** decide session-profile, device, language, or long-term collection cadence. Those remain separate roadmap tasks so depth is not confounded with several observation dimensions at once.

## Experiment identity

```text
spec_version = feed-depth-v1
analyzer_version = 1
feed_parser_version = 2
surface = recommendation_feed
candidate_depths = 1 / 3 / 5 / 10 pages
page_size = 20 requested cards
baseline_language = ru
baseline_device_type = desktop
baseline_platform = desktop_other
baseline_session_profile = clean_anonymous
```

A trial is one logical `ProbeRun` requested at **up to 10 pages**. Depths 1/3/5/10 are derived as prefixes of that same run. Do not collect four independent runs for the four candidate depths: doing so would mix depth effects with time/random/session variation.

If the source legitimately exhausts before page 10, the trial remains eligible. Candidate depths beyond source exhaustion saturate at the final available organic ranking. For example, if the source ends after page 7, the derived depth-10 ranking is the seven-page result; if it ends after page 2, the derived depth-3/5/10 rankings are all the same two-page result. This mirrors real collection semantics: a configured page limit is a maximum, not a promise that the source has that many pages.

Only organic cards participate in depth selection. Sponsored cards remain observable but never count toward organic coverage or rank stability.

Within a trial, an app ID enters the organic ranked list at its first organic occurrence. Repeated organic occurrences on deeper pages do not create additional unique exposure.

## Trial eligibility

A trial is eligible only when all of the following hold:

```text
probe_kind = recommendation_feed
status = completed
requested_page_limit = 10
persisted pages = contiguous prefix from page 0, with 1..10 pages total
if fewer than 10 pages exist, the final page reports source exhaustion
session_profile = clean_anonymous
cookie_state_hash = null
profile_age_days = 0
language = ru
device_type = desktop
platform = desktop_other
every persisted raw page requested games_count = 20
all raw bodies still match their persisted content hashes
all persisted pages can be replayed by YandexFeedParser@2
```

A run that becomes `partial`/`failed`, has a non-contiguous page chain, has missing/tampered raw data, uses a different context, or stops before page 10 without source exhaustion is not silently coerced into an eligible trial.

Operational failures are not evidence that a shallower depth is analytically sufficient. They must be diagnosed separately rather than converted into artificial depth wins.

## Minimum sample before a decision

The report is `insufficient` and must not recommend a depth until it contains at least:

```text
8 eligible trials
4 hours between earliest and latest trial start
3 distinct UTC hour buckets represented by trial starts
```

These are minimum anti-overfitting guards for the first calibration, not claims of statistical power for all future feed behavior.

Do not discard an otherwise eligible trial because its games or stability metrics look unusual.

## Metrics

For each trial and candidate depth `N`:

```text
organic_unique_N
coverage_vs_10_N = organic_unique_N / organic_unique_10
```

When the source exhausted before a candidate depth, that depth uses the final available ranking as described above.

For each candidate depth except 10:

```text
marginal_gain_to_next_N
= (organic_unique_next - organic_unique_N) / organic_unique_next
```

where `next` is the next tested depth (`1→3`, `3→5`, `5→10`).

Across every pair of eligible trials at the same depth, compute:

```text
organic_set_jaccard
ranked_prefix_overlap
```

`organic_set_jaccard` is ordinary Jaccard similarity over unique organic app IDs.

`ranked_prefix_overlap` is a deterministic top-weighted prefix-overlap score with persistence `p = 0.9`. At rank `d`, calculate the overlap ratio between both prefixes through `d`, weight it by `(1-p) * p^(d-1)`, and carry the remaining `p^k` mass at the final evaluated rank `k`. This deliberately emphasizes the top of the feed and supports ranked lists whose memberships differ; do not substitute ordinary Spearman correlation over only the common items.

Report medians for pairwise Jaccard and ranked-prefix overlap. Also report the 25th percentile of per-trial coverage to guard against a depth that looks adequate only on average.

First-page stability is the depth-1 pairwise metric and remains a diagnostic of feed volatility. It is not a separate decision threshold.

## Predeclared decision rule

Evaluate candidates in ascending order: `1`, then `3`, then `5`.

Choose the first depth `N` satisfying **all** of:

```text
median coverage_vs_10_N >= 0.90
25th percentile coverage_vs_10_N >= 0.85
median marginal_gain_to_next_N <= 0.10
median ranked_prefix_overlap_N >= median ranked_prefix_overlap_10 - 0.03
```

Interpretation:

- at least 90% of the full up-to-10-page organic set is captured in a typical trial;
- the lower quartile still captures at least 85%;
- the next tested depth adds no more than 10% median unique organic coverage;
- shallower sampling does not materially reduce top-weighted cross-run rank reproducibility relative to the up-to-10-page baseline.

If no depth in `1/3/5` passes and the sample is sufficient, select **10 pages** as the conservative fallback.

The threshold values above must not be changed after viewing the first experiment outcome. A later threshold change requires a new spec version and a new evaluation.

## Output semantics

The experiment report must include:

```text
spec_version
analyzer_version
feed parser version
submitted trial IDs
eligible trial IDs
rejected trials + reasons
sample size
sample time span
represented hour buckets
per-depth metrics
recommended depth or null
sample_sufficient boolean
decision reasons
```

`recommended_depth = null` when sample sufficiency fails.

The report is calibration evidence, not immutable platform truth. The selected depth becomes the default collection depth for the current observation policy until later evidence justifies a newly versioned calibration.
