# Reaper 0.3 P0 Contract Review — 2026-09-02

**Reviewed scope:** `thesis-intelligence.md` planning semantics plus the frozen 0.3 v1 contracts before implementation.

**Review result:** PASS after corrections below.

The review was performed against the current `main` implementations of:

```text
AnalystExperimentManifest / analyst-experiment-v1.2
AnalystSnapshotReport / analyst-snapshot-v1
AnalystMarketExportReport / analyst-market-export-v1
AnalystMarketFeaturesReport / analyst-market-features-v1
AnalystSemanticThesisDeclaration / analyst-semantic-enrichment-v1
```

The goal was to find places where implementation would otherwise have to invent market semantics, break reproducibility, or duplicate existing runner responsibilities.

---

## Finding 1 — suite compilation could accidentally fork the runner

Risk:

A new thesis-suite coordinator could have introduced its own family/comparable identity or collection lifecycle.

Correction:

The frozen contract now compiles exactly to the existing experiment model:

```text
experiment_id = suite_id
family.id = thesis_id
comparable_set_id = <suite_id>--<thesis_id>
```

Collection/resume/workers/pagination remain exclusively owned by `analyst-experiment-v1.2`.

Status: resolved.

---

## Finding 2 — age-normalized pace needed an explicit young-listing boundary

Risk:

An implementation could silently use `max(age, 1)` or another denominator floor and manufacture a precise-looking pace for a listing only hours old.

Correction:

Frozen method:

```text
age < 1.0 day -> lifetime pace unavailable / too_young
age >= 1.0 day -> rating_count / exact elapsed age days
```

No denominator flooring.

Status: resolved.

---

## Finding 3 — age-bucket percentile denominator was ambiguous

Risk:

“Suite-relative percentile” could mean per-thesis, per-query, duplicate listings across theses, or only rows with observed pace without exposing missingness.

Correction:

The frozen contract now uses:

```text
unique platform listing IDs across the current suite
-> one observed age bucket
-> explicit bucket member count
-> explicit pace-observed count + coverage
-> ECDF percentile over pace-observed rows only
```

Listings returned by several theses are deduplicated in the cohort.

Status: resolved.

---

## Finding 4 — historical velocity could become machine-state dependent

Risk:

A deterministic `build` could read whatever happens to exist in the developer's current SQLite database and produce a different result tomorrow from the same current experiment ZIP.

Real V3 inspection reinforced this: the artifact contained one current `rating_count` point per listing, so genuine longitudinal evidence has to come from separately frozen history.

Correction:

Only explicitly supplied, verified prior experiment ZIPs may contribute prior rating observations. Invocation-local paths are excluded from semantic bindings. Prior bindings are canonically sorted and hash-bound.

Status: resolved.

---

## Finding 5 — same-timestamp prior observations needed conflict behavior

Risk:

Two prior artifacts could expose different rating counts at the same latest timestamp and an implementation might pick one by incidental CLI order.

Correction:

At the greatest eligible prior timestamp:

```text
same value -> deterministic lexical provenance tie-break
conflicting value -> fail closed
```

Status: resolved.

---

## Finding 6 — directness review could become a hidden taxonomy override

Risk:

Allowing arbitrary manual promotions from noise/adjacent into direct inside the review artifact would make semantic rule quality impossible to audit.

Correction:

V1 review scope is explicitly:

```text
direct_candidates only
```

If repeated false negatives are found outside that tail, version/correct the semantic thesis rules instead. Verdict/reason combinations are controlled and frozen.

Status: resolved.

---

## Finding 7 — intelligence artifact path collided across review states

Risk:

The initial conceptual path:

```text
artifacts/intelligence/<suite_id>/<run_id>.zip
```

allows only one create-only artifact for a current experiment. A later rebuild after manual review would collide with the initial no-review artifact.

Correction:

`thesis-intelligence-build-identity-v1.md` now freezes a canonical build-input hash over:

```text
suite hash
method version
current artifact binding
prior artifact bindings
supplied review bindings
```

and publishes to:

```text
artifacts/intelligence/<suite_id>/<run_id>/<build_input_hash>.zip
```

Same inputs are idempotently verifiable/reusable; changed reviews/history create a new immutable artifact rather than overwrite history.

Status: resolved.

---

## Finding 8 — zero-result thesis support would require foundational contract changes

Current inherited constraints include:

```text
AnalystComparableSetBinding.member_listing_ids: min_length=1
AnalystSnapshotDeclaration.rich_metadata_snapshots: min_length=1
AnalystSnapshotPayload.rich_metadata: min_length=1
AnalystSemanticEnrichmentPayload.listings: min_length=1
```

Therefore a truly zero-organic-result thesis is not representable in the current snapshot/semantic chain without versioning several foundational contracts.

Assessment:

- this has not been a demonstrated bottleneck in the real sweeps that motivated 0.3;
- Yandex fuzzy search has instead produced the opposite problem: large noisy unions;
- changing snapshot/export/semantic emptiness semantics would materially expand 0.3 beyond the observed deficiencies.

Decision:

**Do not add zero-member comparable support to 0.3.** Retain the current inherited `>=1` member constraint. If a real focused sweep encounters a true zero-organic union, record it as a new observed blocker and design an explicit versioned empty-comparable path rather than weakening existing v1 contracts ad hoc.

Status: accepted inherited limitation, not an implementation task for 0.3.

---

## Finding 9 — comparison must not imply a winner

Correction confirmed:

- suite declaration order is preserved;
- no automatic sort by traction/opportunity;
- direct evidence is never backfilled with adjacent evidence;
- best-value cells retain listing identity;
- no `BUILD/WATCH/SKIP`, opportunity score, or recommended winner is part of the v1 contract.

Status: resolved.

---

# Final review conclusion

The P0 contracts now answer the market-semantic questions implementation would otherwise have to guess:

```text
what a thesis compiles to
what age means
when lifetime pace is allowed
what cohort a percentile refers to
what historical evidence is eligible
how anomaly missingness behaves
what manual directness review is allowed to change
how search-surface quality is summarized
what appears in per-thesis/cross-thesis reports
how multiple review states remain immutable and reproducible
```

No new collector, scheduler, dashboard, classifier, external trend source, or opportunity scorer is justified by this contract phase.

**P0 review verdict: PASS. P1 implementation may begin after the contract PR passes repository CI and is merged.**
