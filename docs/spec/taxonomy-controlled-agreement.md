# Controlled-Dimension Agreement Analysis

Status: **supporting tooling**. This protocol covers the four frozen high-value controlled multi-label dimensions. It does not complete the Phase 3 agreement gate by itself because real execution is still pending and the separate `theme canonicalization >= 95%` requirement in `taxonomy.md` still needs an explicit validation protocol.

## Purpose

`taxonomy-controlled-dimension-agreement-v1` measures whether independent human annotators apply the frozen v1 controlled-label dimensions consistently:

```text
mechanics
objectives
meta_systems
tones
```

The manual annotation contract already records these dimensions for every sample listing, so ignoring them in agreement analysis would leave the `high-value controlled dimensions >= 90%` pre-freeze target unmeasured.

This protocol is separate from `taxonomy-primary-agreement-v1`. Primary archetypes are mutually exclusive single labels and support symmetric archetype confusion pairs. The controlled dimensions are multi-label sets and require different agreement semantics.

## Evidence boundary

Input is:

1. one exact `taxonomy-diversity-sample-v1` report;
2. one exact revalidated `taxonomy-gold-set-v1` report;
3. every source `taxonomy-manual-annotation-v1` batch referenced by that gold set, in exact persisted source-batch order.

At least two distinct `annotator_id` values are required. Exact immutable batch hashes and distinct identities are machine-checkable; genuine procedural independence before adjudication remains a real-execution requirement.

Every source batch is revalidated against the exact sample and must match the corresponding gold-set `(batch_id, annotator_id, annotation_batch_hash)` reference.

Synthetic fixtures prove mechanics only.

## Frozen v1 identity

```text
spec = taxonomy-controlled-dimension-agreement-v1
contract = controlled-dimension-agreement-v1
contract SHA-256 = 9bebd5221d664ace6b6c046384bed76bbd37153908b4852317cfa74a4832798b
initial controlled-dimension agreement target = 0.90
```

The contract identity binds:

- exact sample/annotation/gold-set protocol identities;
- exact annotation-contract and controlled-registry content hashes;
- the four controlled dimensions in enum order;
- exact registry-label order per dimension;
- report/source/dimension/label-metric field surfaces;
- exact-set pairwise agreement semantics;
- the existing `>= 90%` target;
- deterministic disagreement evidence order;
- zero-denominator behavior for label gold-alignment metrics;
- the boundary against classifier-performance claims, population prevalence claims, and theme canonicalization;
- deterministic JSON content hashing.

## Why exact-set agreement

These dimensions are multi-label. Label order is not semantic, so each annotation is first canonicalized into frozen registry order.

For example:

```text
("merge", "tap")
("tap", "merge")
```

represent the same mechanics set and must agree.

But:

```text
("tap", "merge")
("tap", "match")
```

do not agree merely because both contain `tap`.

For `A` annotators and `N` listings, every dimension evaluates:

```text
pairwise comparisons = C(A, 2) * N
pairwise exact-set agreement = exact canonical set matches / pairwise comparisons
```

V1 operationalizes the existing `high-value controlled dimensions >= 90%` target as **each** of the four frozen dimensions reaching at least `0.90` pairwise exact-set agreement. The report also exposes `all_dimensions_meet_initial_agreement_target`, which is true only when all four pass.

This is intentionally conservative. A looser overlap/Jaccard threshold is not silently substituted for the declared target.

## Per-dimension diagnostics

Every `ControlledDimensionAgreementEntry` records:

```text
dimension
registry_labels[]
pairwise_comparison_count
pairwise_exact_match_count
pairwise_exact_mismatch_count
pairwise_exact_match_rate
initial_agreement_target
meets_initial_agreement_target
unanimous_listing_count
unanimous_listing_rate
disagreement_listing_ids[]
label_metrics[]
```

A listing is unanimous for a dimension only when every supplied annotator produced the same canonical label set.

`disagreement_listing_ids[]` follows exact sample order and provides reproducible evidence anchors for boundary review. With three or more annotators a non-unanimous listing may still contain some agreeing annotator pairs; pairwise counts and unanimous-listing counts therefore answer different questions.

## Per-label gold alignment

Every frozen registry label receives:

```text
gold_support_count
annotation_assignment_count
gold_alignment_true_positive_count
gold_alignment_false_positive_count
gold_alignment_false_negative_count
gold_alignment_precision
gold_alignment_recall
```

Membership is evaluated independently for each label:

```text
TP = annotation contains label and gold contains label
FP = annotation contains label and gold does not contain label
FN = annotation omits label and gold contains label
```

These are **adjudication-alignment diagnostics**, not independent classifier performance. The adjudicated gold set is built from the source annotation batches being analyzed.

If there are no annotation assignments for a label, precision is `None`. If the adjudicated gold set has no support for a label, recall is `None`. Unsupported labels therefore do not acquire fake certainty from a numeric zero denominator.

## Special semantics

The v1 controlled registry rules remain authoritative. In particular, `meta_systems = ("none",)` is exclusive and annotation validation rejects `none` combined with another meta label before agreement analysis begins.

Confidence is recorded once per complete manual classification, not once per controlled dimension. Global low-confidence diagnostics therefore remain in the primary agreement report and are not duplicated as misleading dimension-specific confidence values here.

## Purposive-sample limitation

The diversity sample is not a probability sample. Controlled-dimension agreement describes reproducibility on the reviewed sample and helps identify unstable labels or dimensions. It does not estimate how common a mechanic/objective/meta/tone is across the Yandex Games population.

## Theme canonicalization remains separate

`taxonomy.md` also declares:

```text
theme canonicalization >= 95%
```

The current `taxonomy-manual-annotation-v1` surface does not contain theme canonicalization decisions, and themes are deliberately an open normalized entity layer rather than part of the frozen controlled-label bundle.

Therefore this contract **must not** claim to satisfy the theme target. A separate evidence/annotation/canonicalization protocol is still required before the first validated taxonomy can honestly be frozen unless the owning taxonomy specification is explicitly revised with independent rationale.

## Persisted artifact

`ControlledDimensionAgreementReport` binds exact:

```text
sample identity/hash
gold-set identity/hash
source batch IDs / annotator IDs / annotation hashes
annotation-contract hash
controlled-registry hash
all per-dimension exact-set metrics
all per-label gold-alignment metrics
agreement_content_hash
```

Persisted revalidation rebuilds the report from exact input artifacts and requires exact equality.

## Real execution gate

Do not treat the controlled-dimension target as measured until:

1. the real 100–200-game sample exists;
2. at least two genuinely independent annotation batches cover that exact sample;
3. the real adjudicated gold set binds those exact source batches;
4. `taxonomy-controlled-dimension-agreement-v1` is executed against those artifacts;
5. the real report/hash is recorded and reviewed.

Passing all four controlled dimensions still does not by itself freeze the taxonomy. Primary review/agreement, repeated confusion evidence, explicit `unknown` behavior, taxonomy revision, and the unresolved theme-canonicalization requirement remain separate gates.
