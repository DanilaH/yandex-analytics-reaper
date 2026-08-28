# Evidence Model v2

## 1. Problem with a single confidence class

A single label such as A/B/C/D/E incorrectly mixes source ownership, measurement method, access, semantic certainty, freshness, coverage, and model uncertainty. These dimensions must remain independent.

## 2. Evidence Envelope

Every evidence item has:

```text
evidence_id
source_id
observed_at
period_start
period_end
provenance
measurement_kind
semantic_confidence
freshness_status
coverage_status
point_in_time_integrity
uncertainty
lineage_refs[]
```

## 3. Provenance

```text
first_party
third_party
internal
```

## 4. Measurement kind

```text
observed
estimated
derived
inferred
editorial
```

Examples: ratingCount is observed; estimated installs are estimated; rating_count_delta_7d is derived; primary core loop is inferred; Popular placement is editorial.

## 5. Semantic confidence

```text
high
medium
low
unknown
```

## 6. Freshness

```text
fresh
stale
historical
unknown
```

Always store actual timestamps; freshness label is derived.

## 7. Coverage

```text
complete
partial
sampled
unknown
```

Examples: full paginated query result is complete; first N feed pages are sampled; third-party unknown crawl is unknown.

## 8. Point-in-time integrity

Critical for backtesting:

```text
strict_point_in_time
historical_snapshot
retroactively_recalculated
unknown
```

A retroactively recalculated estimate must not be used as if it was available at historical decision time.

## 9. Uncertainty

When a source provides uncertainty, store point/lower/upper/confidence level. If unavailable, keep it unknown. Do not fabricate ranges.

## 10. Unknown-state semantics

Never collapse all missing values into NULL. Use explicit reason:

```text
not_applicable
not_supported
not_observed
source_missing
source_error
permission_blocked
unknown_semantics
unknown
```

A missing gqRating could mean not yet formed, not observed, source failure, game too small, or unknown. These are not equivalent.

## 11. Decision evidence coverage

For every candidate dossier calculate coverage for core market, history, trends, production, and monetization plus overall evidence coverage.

A strong-looking candidate with poor evidence should usually become WATCH, not BUILD.
