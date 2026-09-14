# R0.4-P2 Known-ID Longitudinal Comparison — Independent Review — 2026-09-14

## Verdict

**IMPLEMENTATION PASS. REAL-DATA ACCEPTANCE REMAINS PENDING.**

The P2 comparator is suitable to merge as the offline comparison capability for already-frozen P1 `point_observed` artifacts. P2 must remain active rather than complete until a second real Keycap observation exists after a meaningful interval.

## Scope reviewed

The implementation adds one bounded operation:

```text
verified earlier point-observation ZIP
+ verified later point-observation ZIP
-> create-only listing-longitudinal-comparison-v1 JSON
```

It does not add a scheduler, collector, search pass, DAU/install/revenue inference, portfolio decision, or new 0.3 Thesis Intelligence semantics.

## Findings repaired before acceptance

### 1. Interpretation boundary initially omitted lifetime pace

The first implementation explicitly rejected interpreting point velocity as search visibility, DAU, installs, revenue or retention, but the R0.4 roadmap also requires point velocity to remain distinct from lifetime pace.

**Fix:** the output now carries the explicit boundary:

```text
point_velocity_not_search_visibility_lifetime_pace_dau_installs_revenue_or_retention
```

This keeps a short observed rating-count interval from being silently presented as lifetime acquisition pace.

### 2. Endpoint source identity was not explicit enough

The first output bound artifact SHA-256, manifest hash, source snapshot/content hash, observation time and parser version. That is cryptographically sufficient to locate the frozen evidence, but the P2 Definition of Done asks for exact artifact/source identity to remain directly visible.

**Fix:** each endpoint now also exposes:

```text
source_id = yandex_public
source_request_key = catalogue.get_games
parser_name = YandexGetGamesParser
parser_version
```

### 3. Initial CI exposed two mechanical line-length failures

The first CI run `34844024061` stopped at Ruff on two E501 lines. No semantic failure was reported because later gates did not run after lint failed.

**Fix:** formatting was repaired together with the semantic hardening above.

## Contract review

The accepted implementation preserves these boundaries:

- both input ZIPs must pass the existing P1 offline verifier first;
- cohort ID/version, declaration hash, exact ordered requested IDs, source surface, parser name and parser version must match;
- `current.observed_at` must be strictly later than `previous.observed_at`;
- output collision fails before input verification/work;
- elapsed seconds and days are explicit;
- `rating_count_delta` and delta/day exist only when both frozen endpoints contain the listing and the metric;
- prior/current listing absence remains `missing_*` rather than zero;
- prior/current metric absence remains `metric_missing_*` rather than zero;
- negative `ratingCount` delta is preserved as `revision_decrease`, not clamped and not described as falling demand;
- positive/zero deltas remain descriptive observations, not inferred DAU, installs, revenue, retention, search visibility or lifetime pace;
- the output binds both input artifact identities rather than depending on file names or mutable paths;
- no network access is needed by the comparator.

## Parser compatibility decision

V1 requires equal parser name **and parser version** across endpoints. This is intentionally conservative. A parser-version transition may be perfectly compatible in reality, but P2 does not yet have a proven cross-version semantic-compatibility contract. Failing closed avoids comparing values whose extraction semantics may have changed invisibly.

A future need may justify an explicit compatibility table/versioned migration. It is not justified now.

## Interval decision

The code does not invent a universal minimum number of hours/days for comparison. The source contract only proves elapsed time and endpoint values; it does not establish a statistically meaningful market-velocity window.

Therefore:

- the comparator may technically compare any strictly ordered frozen observations;
- **real Keycap acceptance must wait for a meaningful later observation**;
- same-day repetition must not be used to close P2 or promoted as current market velocity.

## Quality gate

Clean CI run `34844286971` passed after review fixes:

- Ruff — PASS;
- strict mypy — PASS;
- pytest + coverage — PASS.

Tests cover positive delta, negative revision delta, missing previous/current listing evidence, missing metric evidence, exact elapsed-time normalization, create-only fail-fast behavior, incompatible cohort rejection and reverse-time rejection.

## Decision

Merge is acceptable once README/ROADMAP are synchronized and the final branch CI remains green.

Roadmap state after merge should be:

```text
R0.4-P2 — ACTIVE
implementation complete
real Keycap second-observation validation pending
R0.4-P3 — blocked by the ordered P2 real-data gate
```
