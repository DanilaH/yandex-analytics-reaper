# Reaper 0.3 P5 Review — 2026-09-02

**Scope:** per-thesis intelligence reports and cross-thesis descriptive comparison only.

**Verdict:** PASS after CI/type/fixture corrections.

## Contract compliance

P5 binds the already-shipped P2/P3/P4 evidence into one `thesis-intelligence-report-v1` per thesis and one suite-level `thesis-comparison-v1`.

The comparison remains descriptive. It does not calculate or emit an opportunity score, winner, ranking, recommendation, BUILD/WATCH/SKIP state, market-size estimate, or production-burden estimate.

Rows follow thesis declaration order exactly.

## Review findings

### 1. Strict direct/adjacent separation is preserved

Confirmed-direct metrics are derived only from analyst review rows with `analyst_verdict=confirmed_direct`.

`best_adjacent_rating_count` is derived only from semantic `adjacent_candidate` rows. Adjacent evidence does not substitute for missing confirmed-direct evidence.

The no-review test confirms that a thesis may expose adjacent evidence while all confirmed-direct highlights remain null.

### 2. Fresh/recent semantics match the frozen boundary

P5 uses:

```text
listing_age_days <= 180.0
```

for both fresh confirmed-direct counting and the descriptive recent-release share.

The recent-release share denominator is only rows with observed age. `recent_release_coverage_ratio` separately exposes the observed-age fraction of the full comparable set, so missing age is not silently treated as old or fresh.

### 3. Metric highlights are deterministic and evidence-honest

Highlights choose the maximum usable metric and break equal-value ties by earliest frozen comparable-row order.

`rating_count` highlights retain the source observation ID.

`lifetime_ratings_per_day` is a derived metric, so its highlight deliberately carries `observation_id=null` instead of pretending that one raw observation owns the derived value.

### 4. Longitudinal coverage does not overstate history

Only P2 statuses `observed` and `negative_revision` count as usable longitudinal evidence.

`current_missing`, `no_prior_observation`, and `interval_too_short` remain outside the usable longitudinal denominator numerator. Negative revisions remain usable observations but are not interpreted as negative traffic.

### 5. P3 candidate ordering remains a relational build invariant

`ThesisIntelligenceReport` stores the ordered candidate listing IDs from the validated P3 `ThesisAnomalyQueue`.

The report model can independently prove candidate uniqueness and qualification membership, but it cannot reconstruct P3's pace/rating/age sort key because those sort facts are intentionally owned by the P3 queue artifact.

This is not a reason to duplicate P3 sort metadata into P5. `build_thesis_intelligence_reports()` consumes the already-validated P3 queue and copies its candidate order exactly. Final source-bound rebuild/verification belongs to P6 artifact verification.

### 6. Comparison scalar reconstruction belongs at the correct layer

`build_thesis_comparison()` deterministically derives every comparison scalar/highlight from hash-bound thesis reports plus semantic/review evidence.

The standalone comparison model verifies its own hash, shape, suite declaration order, and thesis-report hashes. It does not duplicate the whole derivation engine inside a Pydantic validator.

P6 is the correct place to verify a packaged artifact by reloading its frozen sources and reconstructing the expected reports/comparison before accepting the ZIP.

### 7. CI exposed two implementation/test defects and both were corrected without weakening gates

Initial branch failures were:

1. strict mypy caught reuse of the local name `report` for both `ThesisIntelligenceReport` and `ThesisComparisonReport`; fixed by explicit `thesis_report` / `comparison_report` names, with no ignore or `Any` escape;
2. the P5 fixture passed a `datetime` into M1.7 `AnalystSemanticSourceReference.retrieved_at`, whose shipped contract is an ISO timestamp string; fixed to the real `...Z` shape rather than changing production semantics.

## Existing focused acceptance coverage

The P5 tests verify:

- suite declaration-order report/comparison rows;
- no ranking/winner output;
- confirmed-direct vs adjacent separation;
- missing-age recent-release denominator and explicit coverage;
- equal-metric comparable-order tie-break through the two equal-rating digicam rows;
- derived lifetime-pace provenance (`observation_id=null`);
- no-review behavior;
- reordered comparison rows rejected even with a recomputed content hash;
- create-only JSON/CSV/Markdown outputs;
- Markdown explicitly states that no winner is implied.

## Quality gate

Final reviewed code baseline passed:

```text
ruff
strict mypy
full pytest: 400 passed
repository coverage gate >= 80%
```

## Scope decision

P5 stops here. It does **not** absorb:

```text
CLI orchestration
final intelligence ZIP packaging
source-bound package verifier
runner/resume redesign
real V3 replay
Satisfying Destruction collection
package version bump
```

Those remain P6/P7 responsibilities.

**Review verdict: PASS. P5 is safe to merge after the final docs-only CI; P6 becomes the next tooling step.**
