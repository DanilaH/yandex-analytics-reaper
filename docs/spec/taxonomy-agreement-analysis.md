# Primary Archetype Agreement / Confusion Analysis

Status: **supporting tooling**. The Phase 3 roadmap item `confusion analysis / agreement analysis` remains incomplete until this protocol is executed against real independent annotation batches over the completed real taxonomy sample.

## Purpose

`taxonomy-primary-agreement-v1` measures whether the draft primary gameplay-archetype registry is being applied consistently by independent human annotators and exposes the label pairs that repeatedly attract different judgments.

This is deliberately separate from `taxonomy-primary-archetype-validation-v1`:

- primary validation is a manual schema/boundary review over adjudicated gold labels;
- agreement analysis uses the pre-adjudication decisions from genuinely independent annotators;
- adjudication must never be compared with itself and reported as human agreement.

## Evidence boundary

The analyzer accepts:

1. one exact `taxonomy-diversity-sample-v1` report;
2. one exact revalidated `taxonomy-gold-set-v1` report;
3. every source `taxonomy-manual-annotation-v1` batch referenced by that gold set, in the exact persisted source-batch order.

At least two source annotation batches with distinct `annotator_id` values are required. The code can prove distinct identities and exact immutable batch hashes; it cannot prove that humans actually worked independently. Real execution therefore still requires the annotation procedure to have produced the batches independently before adjudication.

Every supplied batch is revalidated against the exact sample. Its `(batch_id, annotator_id, annotation_batch_hash)` tuple must exactly match the corresponding gold-set source reference. A convenient substitute batch or a reordered source set is rejected.

Synthetic fixtures prove mechanics only. They are not an empirical agreement result.

## Frozen v1 identity

```text
agreement spec = taxonomy-primary-agreement-v1
agreement contract = primary-archetype-agreement-v1
contract SHA-256 = e09af2c913058837724d51fad30a0b29e95faf7dd2d00ce91a99ccb0506e368f
initial primary agreement target = 0.90
```

The contract identity binds:

- exact sample, annotation, gold-set, annotation-contract, and controlled-registry identities;
- the complete primary-archetype registry including `other` and `unknown`;
- report/source/confusion/class field surfaces;
- the pairwise agreement formula;
- the initial `>= 90%` target already declared in `taxonomy.md`;
- symmetric confusion semantics and deterministic ordering;
- zero-denominator behavior for per-class gold alignment;
- special-state / low-confidence diagnostics;
- the rule that these metrics do not estimate market prevalence or automatically freeze the taxonomy;
- deterministic JSON content hashing.

Once real agreement evidence references v1, semantic changes require a new agreement contract/content identity rather than an in-place mutation.

## Pairwise primary-archetype agreement

For `A` independent annotators and `N` sample listings, v1 evaluates every annotator pair on every listing:

```text
pairwise comparisons = C(A, 2) * N
pairwise agreement rate = matching primary assignments / pairwise comparisons
```

This keeps the metric well-defined for two or more annotators without selecting one annotator as truth.

The report records:

```text
source_batch_count
pairwise_comparison_count
pairwise_agreement_count
pairwise_disagreement_count
pairwise_agreement_rate
initial_primary_agreement_target
meets_initial_primary_agreement_target
```

`meets_initial_primary_agreement_target` is a diagnostic against the existing `0.90` target. Passing it does **not** by itself validate, revise, or freeze the taxonomy. Boundary review, confusion evidence, support, `unknown`, and low-confidence behavior still matter.

## Unanimous listing agreement

Pairwise agreement can hide whether a listing had one dissenting annotator. The report therefore separately records:

```text
unanimous_listing_count
unanimous_listing_rate
disagreement_listing_ids[]
```

A listing is unanimous only when every supplied independent annotator chose the same primary archetype. `disagreement_listing_ids[]` follows exact sample order so the problematic games can be reviewed reproducibly.

## Symmetric confusion analysis

Without an independent truth label, annotator A → annotator B is not a meaningful directional confusion matrix. V1 therefore records disagreements as **unordered primary-archetype pairs** in registry order.

For example:

```text
merge <-> match
shooter <-> survival
other <-> unknown
```

Each `PrimaryArchetypeConfusionPair` records:

```text
archetype_a
archetype_b
comparison_count
comparison_rate
listing_ids[]
```

`comparison_count` counts every annotator-pair disagreement. `comparison_rate` uses all pairwise comparisons as the denominator, so confusion-pair rates sum to the overall disagreement rate.

`listing_ids[]` are unique evidence anchors, not counts. With three or more annotators, one listing can contribute more than one pairwise comparison and can legitimately appear in more than one confusion pair.

Confusion pairs are ordered deterministically by:

1. descending `comparison_count`;
2. primary registry order of `archetype_a`;
3. primary registry order of `archetype_b`.

This makes the largest repeated boundary conflicts visible without pretending one annotator is ground truth.

## `unknown`, `other`, and confidence diagnostics

Across **independent annotation assignments**, not adjudicated labels, the report records:

```text
low_confidence_assignment_count/rate
unknown_assignment_count/rate
other_assignment_count/rate
```

These diagnostics matter because a nominally high raw agreement rate can still hide a taxonomy that pushes difficult cases into `unknown`, or a registry whose boundaries routinely require low-confidence guesses.

`unknown` and `other` remain distinct throughout the analysis.

## Gold-alignment precision / recall

`taxonomy.md` asks for per-class precision/recall before the first taxonomy freeze. For manual annotation analysis, v1 exposes those quantities with deliberately explicit names:

```text
gold_alignment_precision
gold_alignment_recall
```

For each primary archetype, every independent annotation assignment is compared with the final adjudicated gold label:

```text
TP = annotation == class and gold == class
FP = annotation == class and gold != class
FN = annotation != class and gold == class
```

The report also stores:

```text
gold_support_count
annotation_assignment_count
gold_alignment_true_positive_count
gold_alignment_false_positive_count
gold_alignment_false_negative_count
```

Important interpretation boundary: the adjudicated gold set is produced from these source annotation batches, so these values are **adjudication-alignment diagnostics**, not independent classifier performance and not an unbiased estimate of human accuracy.

If a class has no annotation assignments, precision is `None` rather than fake `0`. If the adjudicated gold set has no support for a class, recall is `None`. Unsupported classes therefore cannot acquire misleading precision/recall confidence.

Class metrics follow the full primary registry order, including `other` and `unknown`.

## Purposive-sample limitation

The taxonomy sample is purposive diversity sampling, not a representative probability sample. Therefore:

- agreement/confusion describes consistency on the reviewed gold-set sample;
- class support is diagnostic coverage;
- confusion-pair frequency is useful for taxonomy revision;
- none of these rates estimate Yandex Games population prevalence.

## Persisted artifact

`PrimaryArchetypeAgreementReport` binds exact:

```text
sample identity/hash
gold-set identity/hash
source batch IDs / annotator IDs / immutable batch hashes
annotation-contract hash
controlled-registry hash
all agreement/confusion/class diagnostics
agreement_content_hash
```

Persisted revalidation rebuilds the report from the exact sample, gold set, and source annotation batches and requires exact equality.

## Real execution gate

Do **not** mark `confusion analysis / agreement analysis` complete until:

1. the real 100–200-game sample exists;
2. at least two genuinely independent real annotation batches cover that exact sample under the frozen annotation contract;
3. the real adjudicated gold set binds those exact batches;
4. `taxonomy-primary-agreement-v1` is executed against those artifacts;
5. the real agreement/confusion report and content hash are recorded and reviewed.

Do not generate fake annotators, compare a gold set with itself, or use synthetic fixture agreement as evidence for taxonomy revision/freeze.
