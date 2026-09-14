# Reaper R0.4 — Evidence Completeness v1

## Status

**Milestone:** R0.4  
**Purpose:** improve decision-grade evidence quality after real Reaper usage exposed gaps that search-derived Thesis Intelligence cannot close honestly on its own.

This specification is additive to Reaper 0.3. It does **not** modify the frozen `thesis-suite-v1`, `thesis-intelligence-method-v1`, experiment artifact binding, analyst-review or build-identity contracts.

The core correction is:

```text
search-derived discovery evidence
!=
known-listing point evidence
!=
external / analyst-supplied supplemental evidence
```

All three may support one decision, but their provenance and coverage must remain distinct.

---

## 1. Problems proven by real usage

### 1.1 Search recall is not listing existence

The Sep-14 Keycap traction pass showed that a known direct listing can remain outside the first three Yandex search pages even when queried by exact title. Expanding synonyms cannot guarantee recovery.

Therefore a listing that is already decision-relevant must not depend on rediscovery through search before it can be observed again.

### 1.2 Longitudinal evidence should follow known IDs directly

Thesis Intelligence already computes observed rating deltas when trustworthy frozen prior experiment artifacts exist. That is correct and remains frozen.

The missing capability is a cheap immutable observation artifact for an explicit known-ID cohort, so repeated evidence does not require recollecting a whole search experiment.

### 1.3 Rich Yandex metadata collection already exists

`YandexRichMetadataCollector` and the current analyst experiment runner already collect `catalogue.get_games` evidence raw-first, validate schema drift and persist normalized metadata.

R0.4 must reuse that path. It must not introduce a second rich-metadata parser, source client or normalization model.

### 1.4 Important external evidence is currently weakly packaged

App-store traction, trend pages, external product pages, screenshots and analyst observations may materially influence a thesis, but today they are commonly preserved in prose/chat/research notes rather than one hash-bound supplemental artifact.

R0.4 adds an explicit ingestion boundary for analyst-supplied evidence. It does not turn Reaper into a general web crawler.

---

## 2. Evidence channels

Every decision-relevant listing/evidence record must expose its channel rather than being flattened into one competitor set.

### `search_discovered`

The listing was present in a frozen search-derived experiment/comparable surface.

Rules:

- keeps existing query/rank/page provenance;
- contributes to search-union/supply descriptors;
- absence outside the sampled search surface proves nothing about platform-wide absence.

### `point_observed`

The listing ID was supplied explicitly and observed through a supported exact-ID Yandex surface.

Rules:

- does **not** become a search-union member merely because it was observed;
- does not invent rank, query contribution or search supply;
- is valid for listing-specific metadata/metric history when the raw evidence supports it.

### `supplemental_attached`

Evidence was supplied by an analyst from outside the frozen Yandex collection path and attached/hash-bound locally.

Rules:

- source identity, observation time, evidence kind and attachment digest are explicit;
- analytical meaning is limited to the declared claim/measurement;
- it never masquerades as first-party Yandex evidence.

### `reference_only`

Only a mutable URL/reference was preserved.

Rules:

- weaker than attached evidence;
- cannot be treated as immutable replayable proof;
- must remain visibly marked `reference_only` in downstream packages.

---

## 3. Listing Observation Set v1

### 3.1 Declaration

Introduce `listing-observation-set-v1` as an explicit ordered exact-ID cohort declaration.

Required semantics:

```text
spec_version = listing-observation-set-v1
observation_set_id
observation_set_version
ordered yandex app IDs
requested source surfaces
```

V1 starts with `catalogue.get_games` because that path is already raw-first, schema-guarded and normalized. Game-page observation may be added only when a real decision requires fields not available through the catalogue path.

Constraints:

- IDs must be unique positive integers;
- declaration order is preserved;
- V1 may cap one set at the supported exact-ID batch boundary rather than invent generic chunking infrastructure prematurely;
- source collection uses the existing Yandex public client and rich-metadata collector.

### 3.2 Requested vs returned identity

The artifact must preserve separately:

```text
requested_app_ids
returned_app_ids
missing_app_ids
unexpected_app_ids
```

A requested ID omitted by a successful source response is **missing evidence**, not `ratingCount = 0`, not unpublished/deleted, and not a silent drop.

Unexpected IDs must fail closed unless the source contract explicitly proves why they are legitimate.

### 3.3 Immutable artifact

A point-observation artifact must be self-contained enough for offline verification after collection.

Minimum members:

```text
declaration.json
observation.json
raw metadata
exact raw response bytes
manifest.json
```

The manifest binds every member by path, byte size and SHA-256. Artifact identity includes the declaration content hash and exact raw-source content identity.

Verifier duties:

1. validate member inventory/hashes;
2. replay the exact raw `get_games` response with the declared parser version;
3. reconstruct returned/missing identities;
4. reconstruct supported listing metric facts;
5. require reconstructed observation content to equal the packaged observation.

No network access is permitted during verification.

---

## 4. Longitudinal known-ID evidence

R0.4 must support comparing compatible point-observation artifacts for the same explicit listing cohort.

V1 longitudinal facts are descriptive and source-bounded:

```text
rating_count_previous
rating_count_current
rating_count_delta
elapsed_seconds / elapsed_days
observed_rating_delta_per_day
revision_status
```

Rules:

- velocity requires at least two trustworthy frozen observations;
- negative deltas are preserved and marked as revisions rather than clamped;
- missing current/prior observations remain missing;
- cohort membership is explicit and stable;
- a point-observed delta does not imply search visibility, DAU, installs, revenue or retention.

The first version may require explicit artifact inputs. It does not require a scheduler.

---

## 5. Supplemental Evidence Bundle v1

Introduce `supplemental-evidence-bundle-v1` as an immutable analyst-owned package for evidence that Reaper does not collect directly.

Each record requires:

```text
evidence_id
binding target (thesis and/or listing)
source_kind
source_url or source_reference
observed_at / retrieved_at when known
measurement_kind / claim_kind
value or concise claim
units when applicable
analyst semantic confidence
attachment reference when available
notes
```

Useful source/claim kinds include, without claiming a closed taxonomy:

```text
app_store_listing
external_trend_page
indexed_web_page
review_sample
screenshot
visual_review
analyst_observation
```

### Attachment semantics

When bytes are available, include them and bind exact size/SHA-256 in the bundle manifest.

When bytes are not available, the record must be `reference_only`; a URL must never be hashed and presented as if it froze the destination content.

### Human qualitative annotations

Human judgments may live inside this bundle as explicitly analyst-owned observations, for example:

```text
thumbnail_hook
visual_quality
visual_gameplay_legibility
before_after_readability
review_incentive_contamination
content_factory_risk_note
```

These are annotations, not source measurements and not automatic scores.

R0.4 does not add a screenshot classifier, LLM judge or production-burden model.

---

## 6. Thesis Evidence Pack v1

Do not mutate `thesis-intelligence-build-inputs-v1`.

Introduce an additive `thesis-evidence-pack-v1` envelope that binds already-immutable artifacts:

```text
existing verified Thesis Intelligence artifact
+ zero or more Listing Observation Set artifacts
+ zero or more Supplemental Evidence Bundles
-> one immutable evidence-pack identity
```

The envelope owns binding and provenance only. Existing Thesis Intelligence reports remain unchanged and independently verifiable.

Downstream analyst summaries must keep channel-specific counts/facts visible. Point-observed listings must not inflate search-union supply or confirmed-search competitor counts.

No automatic winner or `BUILD / WATCH / SKIP` decision is added.

---

## 7. Sequencing constraints

R0.4 implementation order is deliberate:

```text
P0 contracts + independent review
-> P1 exact-ID point observation artifact
-> P2 explicit longitudinal comparison
-> P3 supplemental evidence bundle
-> P4 thesis evidence-pack integration
-> P5 real-data validation
-> optional later scheduled watch only after artifact acceptance
```

Do not start with scheduling. A scheduler would automate an evidence contract that has not yet earned stability.

Do not add generic workflow/DAG infrastructure. The first consumers are concrete known-listing observations and bounded analyst-supplied evidence.

---

## 8. Real-data acceptance controls

### Keycap

The first point-observation validation cohort should include known direct IDs:

```text
540402
559445
553722
```

Acceptance requires preserving `553722` even though the Sep-14 search surface missed it, without inserting it into the historical search union.

A later second observation of the same cohort is the first real longitudinal validation for point-observed delta semantics.

### Decorated Mail

The zero-confirmed-direct bounded search result remains unchanged.

External trend/adjacent evidence may be bound through a supplemental bundle, but must remain visibly external and must not be converted into Yandex demand proof.

---

## 9. Explicit non-goals

R0.4 does not add:

```text
new Yandex search algorithm
uncontrolled query expansion
second rich-metadata collector
automatic competitor truth
market-size estimation
DAU / revenue inference
visual ML / LLM classifier
generic web crawler
app-store/trend connectors in P0-P4
generic scheduler / daemon
new dashboard
production-burden scoring
automatic portfolio decision
cross-platform entity-resolution engine
```

The intended gain is narrower and more valuable: **less evidence lost outside search, better real longitudinal observations, and one reproducible package for the manual evidence we already rely on.**
