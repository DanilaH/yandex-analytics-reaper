# Primary Gameplay-Archetype Validation Review

Status: **supporting tooling**. The Phase 3 roadmap item `validate primary gameplay-archetype labels` remains incomplete until this protocol is executed against a completed real sample and real adjudicated gold set.

## Purpose

`taxonomy-primary-archetype-validation-v1` records a structured manual review of the current modeled primary gameplay archetypes against one exact adjudicated gold set.

It answers:

- which modeled archetypes are actually represented in the gold set;
- how many adjudicated examples support each represented archetype;
- what confidence distribution appears inside each archetype;
- how often adjudication ends in the special states `unknown` or `other`;
- whether a reviewer currently recommends keeping a label boundary or treating it as a revision candidate.

It deliberately does **not** calculate annotator agreement, a confusion matrix, precision/recall, or the `>= 90%` agreement target from `taxonomy.md`. Those belong to the separate `confusion analysis / agreement analysis` roadmap task.

The protocol also does not automatically declare the taxonomy valid from support counts alone. A purposive 100–200-game sample is designed to expose label boundaries, not to prove market prevalence or statistical completeness.

## Evidence boundary

Input is:

1. the exact `taxonomy-diversity-sample-v1` report;
2. the exact revalidated `taxonomy-gold-set-v1` report bound to that sample;
3. one `PrimaryArchetypeValidationDeclaration` containing explicit reviewer dispositions.

The gold set is revalidated before any review metrics are produced. A validation declaration must reference the exact `gold_set_id` and `gold_set_content_hash`.

Synthetic sample/gold fixtures prove mechanics only and are not a primary-label validation result.

## Modeled labels vs special states

The current modeled review registry is every `PrimaryGameplayArchetype` except:

```text
other
unknown
```

`other` and `unknown` remain first-class taxonomy values, but they are diagnostics rather than modeled label-review rows:

- `other` means the game is understood but falls outside the current modeled registry;
- `unknown` means available evidence is insufficient for a reliable primary classification.

The report records counts/rates for both states separately.

## Frozen review dispositions

Each modeled archetype receives exactly one disposition:

```text
keep
revise_boundary
merge_candidate
split_candidate
rename_candidate
remove_candidate
insufficient_evidence
```

These are **review findings**, not automatic taxonomy mutations. The later `revise taxonomy` task decides what schema changes actually happen.

Semantics:

- `keep` — current broad aggregation boundary remains plausible from reviewed examples;
- `revise_boundary` — label may remain, but its inclusion/exclusion boundary needs change;
- `merge_candidate` — reviewer sees evidence that the label may not be distinct enough from another archetype;
- `split_candidate` — reviewer sees materially different gameplay patterns currently collapsed together;
- `rename_candidate` — boundary may be workable but the current name is misleading or underspecified;
- `remove_candidate` — reviewer sees evidence the modeled archetype may not deserve an independent primary bucket;
- `insufficient_evidence` — current gold evidence is not enough to make a substantive disposition.

The v1 contract SHA-256 content identity is:

```text
83d983d0062d61a6fb434b9b18debc536aba712b7a31ee584fdb7268f8f93d57
```

It covers:

- the validation spec and review-contract versions;
- the exact `taxonomy-diversity-sample-v1` and `taxonomy-gold-set-v1` input protocol versions;
- the frozen manual annotation-contract content hash;
- exact modeled archetype order and `other` / `unknown` special states;
- exact disposition registry;
- declaration, review-row, report-entry, and report field surfaces;
- the 100–200 reviewed-label bounds;
- exact gold-set binding, review-order, evidence, rationale, zero-support, and insufficient-evidence rules;
- UTC datetime canonicalization and deterministic JSON content-hash canonicalization;
- the rule that support diagnostics are not automatic validation thresholds;
- the separation from agreement/confusion analysis.

Because no real primary-archetype review had used v1 yet, this identity was completed before first empirical use rather than preserving an incomplete decorative hash.

## Declaration

A declaration records:

```text
spec_version = taxonomy-primary-archetype-validation-v1
validation_contract_version = primary-archetype-review-v1
review_id
reviewer_id
gold_set_id
gold_set_content_hash
reviewed_at
reviews[]
```

`reviewed_at` must be timezone-aware and is canonicalized to UTC.

`reviews[]` must contain every modeled primary archetype exactly once and in enum/registry order. `other` and `unknown` cannot appear as review rows.

Each review contains:

```text
archetype
disposition
evidence_listing_ids[]
rationale
```

Rationale is always required, nonblank, and already trimmed. Evidence IDs are normalized to trimmed IDs, must be nonblank, and must be unique within a review row.

Evidence IDs are manual anchors into the exact adjudicated gold set. Every cited listing must itself be adjudicated to the archetype being reviewed. A substantive disposition other than `insufficient_evidence` requires at least one cited listing.

If the gold set contains **zero** examples of an archetype, v1 forces `insufficient_evidence`. A reviewer cannot mark an unobserved label `keep` merely because its definition seems reasonable in the abstract. Conversely, a supported archetype may still receive `insufficient_evidence` when the available examples are not enough to make a confident boundary judgment.

## Report diagnostics

For every modeled archetype the report records:

```text
support_count
support_rate
high_confidence_count
medium_confidence_count
low_confidence_count
all adjudicated listing IDs
manual disposition
manual evidence listing IDs
rationale
```

Global diagnostics include:

```text
total labels
modeled-label count
unknown count/rate
other count/rate
high / medium / low confidence counts
modeled labels with support
modeled labels without support
revision-candidate count
```

`revision_candidate_count` counts dispositions other than `keep` and `insufficient_evidence`. It is descriptive, not an automatic failure threshold.

The persisted report stores exact sample/gold identities, frozen validation and annotation contract hashes, and `validation_content_hash`. Revalidation rebuilds the report from the exact sample, gold set, and declaration and requires exact equality.

## Separation from agreement/confusion analysis

This protocol evaluates the **reviewability and apparent boundary quality** of the label registry using adjudicated gold examples. It must not be reported as inter-annotator agreement.

The later agreement/confusion task consumes genuinely independent annotation batches and may measure:

- overall primary-archetype agreement;
- per-label confusion pairs;
- low-confidence concentration;
- confusion involving `unknown` / `other`;
- the existing initial `>= 90%` primary-archetype agreement target.

Keeping those calculations separate prevents adjudicated labels from being compared with themselves and called agreement.

## Real execution gate

Do **not** mark `validate primary gameplay-archetype labels` complete until:

1. the real 100–200-game sample execution is complete;
2. the real manual gold-set execution is complete;
3. a real reviewer declaration covers every modeled archetype under the frozen v1 protocol;
4. the resulting real validation report/hash is recorded.

No taxonomy revision/freeze decision may claim this validation step is complete from synthetic fixtures.
