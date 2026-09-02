# Reaper 0.3 P1 Review — 2026-09-02

**Scope:** thesis-suite compiler, experiment-artifact bindings, canonical history/review ordering, and build identity only.

**Verdict:** PASS after corrections.

## Contract compliance

P1 reuses the existing `analyst-experiment-v1.2` model rather than introducing another collection runtime:

```text
suite_id -> existing experiment_id
thesis_id -> existing family.id
queries -> existing family.queries
<suite_id>--<thesis_id> -> existing comparable-set identity
```

M1.7 semantic declarations are compiled to the shipped `analyst-semantic-thesis-v1` model with an exact target comparable-set ID.

No collection, resume, worker, pagination, SQLite schema, traction, anomaly, review, or comparison behavior was added in P1.

## Review findings and corrections

### 1. Caller-trusted artifact binding was insufficient

Initial implementation could accept a structurally valid `ExperimentArtifactBinding` without proving that the fields came from the claimed experiment ZIP.

Corrected P1 adds `load_experiment_artifact_binding()` which first invokes the existing packaged-artifact verifier and then reconstructs/checks:

```text
artifact manifest
-> input experiment manifest
-> execution summary
-> analyst snapshot
-> market export
-> market features
-> verification report
```

The binding is emitted only after experiment/run identities and report hashes agree.

For a current artifact, the embedded experiment manifest can additionally be required to equal the manifest deterministically compiled from the supplied thesis suite.

### 2. Build path validation was too self-referential

The first model implementation recovered `suite_id` from `relative_artifact_path` and used that same value to validate the path. A manually constructed model could therefore choose a different well-formed suite path.

Corrected build identity carries explicit `suite_id` / `suite_version` metadata and derives the expected path from that suite identity plus the canonical build-input hash.

The build-input hash itself remains exactly the frozen P0 contract: suite content hash + method version + current/prior/review bindings.

### 3. Existing verifier exception leaked across layer boundary

`verify_packaged_artifact()` raises `AnalystExperimentError`, while P1 initially normalized only ZIP/Pydantic/value failures.

Corrected loader converts existing verifier failures to the 0.3 `ThesisIntelligenceError` boundary while preserving the cause.

### 4. Canonical history ordering is independent of CLI order

Verified in tests:

```text
snapshot_created_at
-> experiment_id
-> run_id
-> artifact_sha256
```

Changing the order in which the same prior artifacts are supplied cannot change the resulting build identity.

Review bindings are canonicalized to suite thesis declaration order.

### 5. Review state changes build identity

Verified in tests: the same frozen experiment with and without a review binding produces different `build_input_hash` values and therefore different create-only artifact paths.

### 6. Timestamp offsets do not change canonical identity

Equivalent aware timestamps are canonicalized to UTC `Z` before hashing. Tests confirm equivalent instants with different offsets hash identically.

## Real V3 compatibility check

The real frozen V3 experiment artifact (`20260901T173529Z`) was inspected against the P1 loader contract.

Required members were present:

```text
input/manifest.json
reports/analyst-snapshot.json
reports/market-export.json
reports/market-features.json
reports/verification.json
execution-summary.json
artifact-manifest.json
```

Observed consistency checks all passed:

```text
artifact/input/summary experiment_id agree
artifact/summary run_id agree
input manifest SHA-256 == execution summary manifest_sha256
snapshot_id agrees across snapshot/export/features
snapshot content hash agrees across snapshot/export/features
summary snapshot/export/features hashes agree with report hashes
verification snapshot/export/features hashes agree with report hashes
verification status == pass
```

This confirms P1 is compatible with the already-produced 0.2 artifact shape used by real thesis research.

## Quality gate

Final P1 head passed:

```text
ruff
strict mypy
full pytest
repository coverage gate
```

## Scope decision

P1 stops here. In particular it does **not** absorb:

```text
age/traction calculation
historical delta calculation
anomaly filtering
manual directness verdicts
competitor quality summaries
cross-thesis comparison
CLI orchestration
package version bump
```

Those remain owned by P2+.

**Review verdict: PASS. P1 is safe to merge; P2 may begin from main after merge.**
