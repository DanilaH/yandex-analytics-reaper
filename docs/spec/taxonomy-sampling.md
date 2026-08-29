# Taxonomy Diversity Sampling

Status: **supporting tooling**. The Phase 3 roadmap item `sample 100–200 diverse Yandex games` remains incomplete until this protocol is executed against real persisted Yandex probe evidence.

## Purpose

`taxonomy-diversity-sample-v1` constructs a reproducible **purposive diversity sample** for manual taxonomy/gold-set work.

It is not a statistically representative market sample and must not be used to estimate Yandex Games genre prevalence. Its job is to expose the draft taxonomy to a broad variety of observed catalogue/search cards so label boundaries can be reviewed before classifier work.

## Evidence boundary

Input is an explicit manifest of already persisted probe-run IDs. Every run must be:

- `source_id=yandex_public`;
- a completed recommendation-feed or search run;
- `clean_anonymous`;
- `ru / desktop / desktop_other`;
- null country/collector region;
- in one exact shared `ProbeContext` cohort.

The sampler replays every persisted page from the immutable raw snapshot store with `YandexFeedParser@2` and requires the reconstructed `ProbePage` to equal the persisted page record.

Raw request metadata must match the persisted run/context/query/pagination linkage. A caller cannot supply an arbitrary list of app IDs and call it the v1 sample.

Sponsored cards are excluded.

## Diversity cues

The sampler uses only source-observed card metadata that already exists in immutable raw evidence:

```text
category_ids[]
tag_ids[]
developer id/name
feed vs exact search-query origin
```

`category_ids` and `tag_ids` are **sampling cues only**. They are not treated as taxonomy labels and their numeric values are not assigned invented semantic meanings.

For a listing observed more than once, the candidate record keeps:

- the union of observed category IDs;
- the union of observed tag IDs;
- all observed developer keys;
- all feed/search origins;
- all raw snapshot/page/source-object-path evidence.

This preserves source variation instead of silently choosing one occurrence.

## Manifest

Example:

```json
{
  "spec_version": "taxonomy-diversity-sample-v1",
  "sample_id": "taxonomy-gold-seed-1",
  "target_size": 150,
  "max_per_developer": 2,
  "run_ids": [
    "probe:...",
    "probe:..."
  ]
}
```

Rules:

- `target_size` must be between 100 and 200;
- default target is 150;
- `max_per_developer` is frozen to exactly 2 in v1 and cannot be tuned after viewing the pool;
- run IDs are explicit and unique;
- the organic unique candidate pool must contain at least `target_size` listings.

Input run order is not a selection signal: run IDs are sorted before replay/reporting.

## Frozen v1 selection rule

For each candidate define feature tokens:

```text
category:<id>
tag:<id>
```

For each token, compute its frequency in the complete candidate pool.

Candidates are then selected greedily. At every step, eligible candidates are ordered by this frozen lexicographic priority:

1. larger inverse-frequency weight of **newly uncovered** category/tag tokens;
2. more previously unseen feed/search origins;
3. larger minimum Jaccard distance from already selected category/tag feature sets;
4. larger total inverse-frequency rarity weight;
5. lexicographically smaller `platform_listing_id` as the deterministic final tie-break.

Inverse-frequency token weight is exactly `1 / pool_frequency(token)`.

The known-developer cap is 2 and is enforced during selection. If the cap prevents reaching the requested target, the sampler fails closed and the input pool must be broadened rather than silently relaxing the rule or changing the cap under the same protocol version.

Candidates without known developer identity are not all collapsed into one fake developer.

## Output and reproducibility

The report records:

```text
spec_version
sample_id
parser name/version
exact context_id
sorted input_run_ids
target_size
max_per_developer
candidate_pool_size
selected members in deterministic ordinal order
  app_id / platform_listing_id
  observed titles
  developer keys
  category/tag IDs
  origin keys
  raw evidence[]
coverage diagnostics
sample_content_hash
```

`sample_content_hash` covers the manifest inputs, exact sorted run IDs, selected members and their raw evidence. Re-running the same manifest against the same immutable evidence must produce the same report/hash.

## Operational workflow

Run:

```bash
yandex-reaper sample-taxonomy-games taxonomy-sample.json --output data/raw
```

The report supplies the selected `app_id` values. Collect richer first-party metadata for manual labeling with the existing `probe-games` command in batches of at most 100 IDs. Rich details/descriptions/media are evidence for later manual classification; they do not alter which listings were selected by this v1 sampler.

## Roadmap completion gate

Synthetic fixtures validate mechanics only.

Do **not** mark `sample 100–200 diverse Yandex games` complete until a real runtime report contains 100–200 real selected Yandex listing IDs with replayable provenance and a recorded `sample_content_hash`.

The later manual gold set may deliberately review/replace taxonomy labels, but it must keep the sample identity/provenance separate from the human labels assigned afterward.
