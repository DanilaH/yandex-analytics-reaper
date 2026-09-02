# Reaper 0.3 — Thesis Intelligence Build Identity v1

**Status:** normative companion to [`thesis-intelligence-contracts-v1.md`](thesis-intelligence-contracts-v1.md)  
**Reason:** independent P0 review found that `<suite_id>/<run_id>.zip` cannot represent multiple valid rebuilds of one frozen experiment with different analyst-review artifacts.

This contract supersedes only the output-path/build-identity wording in section 13 of `thesis-intelligence-contracts-v1.md`. All other frozen v1 semantics remain unchanged.

---

# 1. Canonical build-input identity

Every intelligence build creates one canonical input payload:

```text
ThesisIntelligenceBuildInputsV1
  spec_version: "thesis-intelligence-build-inputs-v1"
  method_version: "thesis-intelligence-method-v1"
  suite_content_hash
  current_experiment: ExperimentArtifactBinding(role=current)
  prior_experiments: canonical tuple[ExperimentArtifactBinding(role=prior), ...]
  review_bindings: tuple[ThesisReviewBindingV1, ...]
```

`ThesisReviewBindingV1`:

```text
thesis_id
review_content_hash
semantic_report_content_hash
```

Review bindings follow suite thesis declaration order and contain only supplied reviews. Omitted reviews do not create placeholder rows.

`suite_content_hash` is SHA-256 over canonical `ThesisSuiteDeclaration` JSON, not over the invocation-local suite file bytes.

The build input hash is:

```text
build_input_hash
= SHA-256(canonical JSON of ThesisIntelligenceBuildInputsV1)
```

Changing any of the following therefore creates a different build identity:

```text
suite declaration/version/policy
current experiment artifact
prior experiment artifact set
prior canonical ordering/content
method version
any supplied analyst review
```

Local paths, current working directory, CLI argument order for prior artifacts, and ZIP extraction directory do not affect the identity.

---

# 2. Output path

The frozen v1 create-only path is:

```text
artifacts/intelligence/<suite_id>/<current-run-id>/<build_input_hash>.zip
```

This allows one immutable experiment to support multiple legitimate intelligence states, for example:

```text
initial build with no manual reviews
later build with direct-candidate reviews
later corrected/versioned review build
```

without overwriting historical artifacts.

The older conceptual path:

```text
artifacts/intelligence/<suite_id>/<run_id>.zip
```

is explicitly superseded and MUST NOT be implemented.

---

# 3. Artifact manifest binding

`thesis-intelligence-artifact-v1` additionally stores:

```text
suite_id
suite_version
current_experiment_run_id
build_input_hash
files: sorted member path/size/SHA-256 entries
```

The manifest does not hash itself.

The canonical member:

```text
bindings/build-inputs.json
```

contains the exact `ThesisIntelligenceBuildInputsV1` payload used to derive `build_input_hash`.

Verification recomputes the build-input hash before checking all member hashes.

---

# 4. Existing-path behavior

Publication remains create-only.

If the exact `<build_input_hash>.zip` already exists:

- verify the existing artifact fully;
- if it binds the same build inputs and all member hashes pass, return/reuse the existing artifact;
- if verification fails or identity differs, fail closed;
- never overwrite it.

This is idempotent rebuild behavior, not mutable artifact publication.
