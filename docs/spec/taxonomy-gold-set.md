# Manual Taxonomy Gold Set

Status: **supporting tooling**. The Phase 3 roadmap item `create manual gold set` remains incomplete until a real `taxonomy-diversity-sample-v1` report is manually annotated and adjudicated.

## Purpose

The manual gold-set workflow creates a traceable human reference artifact for Phase 3 taxonomy validation. It deliberately separates:

1. **independent annotation batches** — what each annotator decided before adjudication;
2. **adjudicated gold labels** — the canonical manual reference chosen after reviewing the source batches.

This separation is required so later agreement/confusion analysis can inspect genuine independent decisions instead of comparing a gold set with itself.

Synthetic fixtures validate mechanics only. They are not a manual gold set.

## Frozen annotation target

`taxonomy-manual-annotation-v1` / `phase3-draft-v1` annotates only the taxonomy surface that Phase 3 currently intends to validate:

```text
primary_archetype
mechanics[]
objectives[]
meta_systems[]
tones[]
confidence
rationale
```

It does **not** require manual labels for themes, trend layers, session model, replayability, social mode, presentation, or monetization. Those fields are outside this validation contract and must not inflate annotation workload implicitly.

The controlled dimensions use label registry v1. Before the first real annotation execution, the v1 annotation contract is frozen with SHA-256 content identity `9815b185ef709cb9275985474970165f16eef8f78ea74e73c1397b38fa646c17` covering:

- the exact manual-label field surface including listing identity, primary label, controlled axes, confidence, and rationale;
- the ordered `PrimaryGameplayArchetype` values;
- the four controlled dimensions;
- the exact confidence values `high / medium / low`;
- the rule that `other` and `unknown` require rationale;
- the rule that `meta_systems=none` is exclusive;
- label-registry version 1;
- the exact label-registry-v1 content hash.

Changing any of those semantics after real annotations exist requires a new annotation-contract version/content identity rather than silently reinterpreting historical labels.

## `unknown` and `other`

The two primary states remain distinct:

- `unknown` — available evidence is insufficient or genuinely ambiguous;
- `other` — the annotator believes the game is understood well enough, but none of the current primary archetypes fits.

Both require an explicit nonblank `rationale`. This prevents either state from becoming an undocumented fallback bucket.

## Independent annotation batch

An input batch records:

```text
spec_version = taxonomy-manual-annotation-v1
annotation_contract_version = phase3-draft-v1
label_registry_version = 1
batch_id
annotator_id
sample_id
sample_content_hash
created_at
labels[100..200]
```

Each label records:

```text
platform_listing_id
primary_archetype
mechanics[]
objectives[]
meta_systems[]
tones[]
confidence = high | medium | low
rationale?
```

`created_at` must be timezone-aware and is canonicalized to UTC before artifact hashing.

Validation requires the batch to cover **every selected sample member exactly once and in the exact sample ordinal order**. Missing, extra, duplicate, reordered, or different-sample members fail closed.

The validator also revalidates Pydantic model instances at the empirical boundary, so unchecked `model_copy(update=...)` mutations cannot bypass the frozen contract.

A validated batch receives `annotation_batch_hash`, which covers the exact sample identity, annotator/batch IDs, UTC timestamp, contract/registry identities, and ordered labels.

## Sample integrity

Gold-set tooling does not trust a sample JSON merely because it contains a 64-character hash string.

Before accepting annotations it verifies:

- 100–200 selected members;
- `selected_count == target_size`;
- candidate pool is not smaller than selected membership;
- contiguous sample ordinals from zero;
- unique/nonblank input run IDs;
- frozen `YandexFeedParser@2` sampling provenance;
- frozen developer cap `2`;
- lowercase SHA-256 shape;
- recomputed `taxonomy-diversity-sample-v1` content hash equals `sample_content_hash`.

The sample-hash recomputation intentionally preserves the sampling-v1 JSON canonicalization instead of retroactively changing that protocol.

## Adjudicated gold set

`taxonomy-gold-set-v1` consumes:

- the exact sample report;
- one explicit gold-set declaration;
- one or more source annotation batches.

The declaration records:

```text
gold_set_id
sample_id
sample_content_hash
adjudicator_id
adjudicated_at
source_annotation_batch_hashes[]
labels[100..200]
```

`adjudicated_at` must be timezone-aware and is canonicalized to UTC.

Every supplied source batch is independently validated against the same sample. Source batch IDs and annotator IDs must be unique. The declared source hashes must exactly equal the validated supplied batches; unreferenced or invented source hashes fail closed.

The final `gold_set_content_hash` covers:

- gold-set and annotation spec identities;
- frozen annotation-contract hash;
- registry version/content hash;
- exact sample identity/hash;
- adjudicator and UTC adjudication time;
- ordered source-batch identities;
- exact ordered adjudicated labels.

A persisted gold-set report can be revalidated later against the exact sample, frozen annotation/registry identities, source-batch references, and its recomputed content hash. Persisted JSON is not trusted solely because it parses.

## Agreement analysis boundary

A gold set may technically be built from one annotation batch, because manual adjudication and inter-annotator agreement are separate roadmap concerns.

However, the later `confusion analysis / agreement analysis` task must not claim inter-annotator agreement unless at least two genuinely independent annotator batches exist for the same exact sample/contract. The gold artifact itself is not a substitute for a second annotator.

## Operational execution gate

Supporting models/validators may be merged before runtime evidence exists under the repository's runtime-evidence-gated roadmap rule.

Do **not** mark `create manual gold set` complete until all of the following are true:

1. the preceding real 100–200-game sampling execution is complete;
2. at least one complete real manual annotation batch validates against that exact sample;
3. an explicit adjudicated `taxonomy-gold-set-v1` artifact is built from validated real annotation batch(es);
4. the real `gold_set_content_hash` is recorded.

No downstream taxonomy validation result may consume synthetic annotations or a gold-set artifact whose real execution item is still pending.
