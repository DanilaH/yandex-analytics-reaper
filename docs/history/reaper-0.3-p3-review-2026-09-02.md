# Reaper 0.3 P3 Review — 2026-09-02

**Scope:** explicit anomaly-policy gates over frozen P2 traction facts and deterministic review-queue ordering only.

**Verdict:** PASS after one structural correction.

## Measurement-honesty boundary

P3 introduces no inferred opportunity score, success probability, market score, profitability estimate, or hidden threshold.

Every gate is read directly from the analyst-owned `thesis-anomaly-policy-v1` declaration and evaluated independently against a named P2 fact.

Gate states remain exactly:

```text
pass
fail
unknown
not_configured
```

A listing qualifies as an `anomaly_candidate` only when every configured gate is `pass`.

`unknown` never qualifies and is never silently converted to zero.

## Disabled policy

When `anomaly_policy = null`:

```text
status = disabled
evaluations = ()
candidates = ()
```

P2 traction remains available; P3 does not invent default anomaly thresholds.

## Longitudinal gate

The observed-delta gate uses only P2 longitudinal evidence.

```text
observed           -> numeric pass/fail
negative_revision  -> numeric pass/fail using the preserved negative value
current_missing    -> unknown
no_prior_observation -> unknown
interval_too_short -> unknown
```

A negative revision is therefore not disguised as missing data. It normally fails a non-negative minimum threshold while remaining explicitly distinguishable from absent history.

## Queue ordering

The frozen ordering is implemented exactly:

```text
1. lifetime_ratings_per_day descending, unavailable last
2. rating_count descending, unavailable last
3. listing_age_days ascending, unavailable last
4. platform_listing_id ascending
```

This ordering is review convenience only and is not rendered or named as a score.

### Review correction — independently verifiable ordering

The initial implementation stored only ordered candidate listing IDs. That made the build deterministic, but a standalone anomaly-artifact validator could not prove that a manually reconstructed/re-hashed payload followed the frozen order without reopening the P2 traction report.

The final P3 candidate entry therefore carries only the descriptive sort facts needed for verification:

```text
platform_listing_id
lifetime_ratings_per_day
rating_count
listing_age_days
```

`ThesisAnomalyQueue` validates its own candidate ordering from these facts. A reversed queue fails model validation even if a caller attempts to recalculate a new content hash.

These fields are not an additional analytical feature set; they are copied P2 facts needed to make the declared ordering auditable.

## Cross-layer bindings

The anomaly report binds:

```text
suite_id
suite_version
suite_content_hash
traction_report_content_hash
explicit anomaly policy
per-thesis evaluation/candidate queues
content_hash
```

The builder rejects a P2 traction report whose suite identity/hash or thesis order/version differs from the supplied suite declaration.

## Test coverage

Focused P3 tests cover:

- null policy -> disabled empty queue;
- pass/fail/unknown/not_configured gate states;
- missing rating/pace/percentile staying unknown;
- unknown never qualifying;
- positive longitudinal velocity passing a configured minimum;
- negative revision remaining numeric and failing the minimum;
- no-prior and short-interval history staying unknown;
- deterministic queue ordering including unavailable pace/rating facts;
- independently rejecting reversed candidate order;
- suite-revision / traction binding mismatch;
- report content-hash tampering;
- impossible disabled-with-policy report state.

## Quality gate

The final code/test head passed:

```text
ruff
strict mypy
full pytest
repository coverage >= 80%
```

## Scope guard

P3 does not implement:

```text
semantic/directness review
competitor-set quality
cross-thesis comparison
winner ranking
production burden
external trends
CLI orchestration
collection changes
schema migration
package version bump
```

Those remain P4+.

**Review verdict: PASS. P3 is safe to merge after the final docs-only CI recheck.**
