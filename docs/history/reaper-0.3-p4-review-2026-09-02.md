# Reaper 0.3 P4 Review — 2026-09-02

**Scope:** hash-bound analyst review of semantic direct-candidate rows plus descriptive competitor/search-surface quality metrics.

**Verdict:** PASS after corrections.

## Contract compliance

P4 remains downstream of the shipped M1.7 semantic classifier. It does not change lexical rules or silently promote adjacent/noise rows.

The review boundary is deliberately narrow:

```text
semantic direct_candidate
-> explicit human verdict
-> confirmed_direct | adjacent | not_direct | unresolved
```

If future research demonstrates false negatives outside the direct-candidate tail, the semantic thesis declaration must be corrected/versioned rather than overridden by P4 review state.

## Review findings and corrections

### 1. Review order is canonical, not analyst-file order

Input decisions may arrive in arbitrary order. The canonical artifact follows the bound semantic report listing order. Validation rejects reordered rows even when a caller recomputes the content hash.

### 2. Review vocabulary is constrained

Verdict/reason pairs are checked against the frozen P0 vocabulary. `reason_code=other` requires a non-blank analyst note. A review cannot target an unknown listing or a semantic row that is not `direct_candidate`.

### 3. Competitor counts stay bounded to the researched surface

`CompetitorQualityV1` reports the frozen comparable union and semantic source/directness counts. It does not reinterpret those counts as total Yandex supply, market size, traffic, demand, or profitability.

The explicit zero-confirmed state remains bounded to the researched surface:

```text
all_direct_candidates_reviewed_zero_confirmed
```

It is not an absolute market-absence claim.

### 4. Query-surface quality uses frozen comparable provenance

Query contribution/coherence is derived only from `AnalystComparableMembership.source_queries` already frozen in the market export.

P4 does not use `totalGamesCount` as saturation and does not issue new Yandex requests.

Per-query facts include:

```text
organic_member_count
unique_contribution_count
members_seen_by_multiple_queries
multi_query_member_share
pairwise intersection / union / Jaccard
mean / median numeric pairwise Jaccard
```

These values describe how the researched query surface overlaps; they do not estimate market size.

### 5. Self-validation was strengthened during review

The final model checks independently verify:

- semantic source coverage counts and ratio;
- directness counts sum to raw researched union;
- direct-candidate share;
- review verdict counts and false-positive accounting;
- review coverage and direct-review state;
- query row uniqueness;
- exact pairwise combination order;
- Jaccard arithmetic and mean/median summaries;
- multi-query count/share consistency;
- existing suite compile identity (`set_version=1`, `query_family_version=1`).

This prevents a structurally valid but semantically inconsistent P4 object from becoming authoritative merely because a caller recomputed a hash.

## Scope check

P4 did **not** add:

```text
semantic classifier changes
adjacent/noise manual override
opportunity score
automatic winner / BUILD / WATCH / SKIP
market-size inference
new Yandex collection
traction/anomaly changes
cross-thesis comparison
CLI orchestration
schema migration
package version bump
```

## Quality gate

The final code/test head passed:

```text
ruff
strict mypy
full pytest
repository coverage gate
```

**Review verdict: PASS. P4 is ready for final documentation synchronization and merge; P5 becomes the next tooling gate.**
