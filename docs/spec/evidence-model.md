# Evidence Model

Evidence quality is multi-dimensional. Do not collapse it into one A/B/C/D/E grade.

## Evidence envelope

Every decision-relevant evidence item records or can derive:

```text
source_id
provenance
measurement_kind
semantic_confidence
coverage_status
historical_availability
revision_status
uncertainty
lineage_refs[]

period_start
period_end
observed_at
available_at
retrieved_at
```

## Provenance

```text
first_party
third_party
internal
```

## Measurement kind

```text
observed
estimated
derived
inferred
```

Editorial/sponsored/organic are exposure-selection semantics, not measurement kinds. An observed placement can have `selection_origin = editorial` while remaining `measurement_kind = observed`.

## Semantic confidence

How certain are we about the field's meaning?

```text
high
medium
low
unknown
```

This is independent of who published the value.

## Coverage

```text
complete
partial
sampled
unknown
```

Examples:

```text
full paginated search result  → complete
first N recommendation pages  → sampled
unknown third-party crawl      → unknown
```

## Time semantics

These timestamps are not interchangeable:

```text
period_start / period_end
= period described by the value

observed_at
= timestamp/state the evidence says it represents

available_at
= earliest time the value was actually available to our decision process

retrieved_at
= when our system physically retrieved it
```

For live first-party collection, `available_at` is normally close to `retrieved_at`. For historical/backfilled datasets it may differ materially.

Strict backtests must enforce:

```text
available_at <= decision_as_of
```

not merely `period_end <= decision_as_of`.

## Freshness

Do **not** store `fresh/stale` as an immutable evidence property. Freshness changes with the evaluation time.

Calculate it at read/decision time:

```text
freshness = f(as_of, available_at/retrieved_at, source cadence, metric semantics)
```

## Historical availability

Whether we can prove the value was available historically:

```text
point_in_time
reconstructed
unknown
```

`reconstructed` evidence may support exploratory retrospective analysis but cannot masquerade as strict pre-build evidence.

## Revision status

Whether a historical value itself can change after first publication:

```text
immutable
revised
retroactively_recalculated
unknown
```

Historical availability and revision status are independent dimensions. A historical snapshot can be point-in-time and immutable; a reconstructed series can be retroactively recalculated.

## Uncertainty

If a source provides uncertainty, store:

```text
point
lower
upper
confidence_level
```

Otherwise keep uncertainty unknown. Never invent ranges.

## Missing values

Never collapse every missing value into `NULL` with no reason.

Supported reasons include:

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

For example, missing `gqRating` may mean the score has not formed, the source did not expose it, collection failed, or the semantics are unknown. Those states are analytically different.

## Decision evidence coverage

Candidate dossiers should report coverage separately for at least:

```text
market state
history
external trends
production assessment
monetization evidence
```

Low evidence coverage should usually push an otherwise attractive candidate toward `WATCH` rather than creating false certainty.
