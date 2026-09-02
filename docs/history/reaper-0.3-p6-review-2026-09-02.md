# Reaper 0.3 P6 review — 2026-09-02

## Verdict

**PASS for P6 scope.**

P6 remains a thin application layer over the accepted 0.2 experiment runner and the already-merged
P1–P5 thesis-intelligence contracts. It does not introduce a second collector, scheduler, mutable
history store, ranking system, or workflow framework.

The review explicitly checked deterministic rebuild behavior, review semantics, create-only artifact
identity, failure isolation, and the boundary between source evidence and derived intelligence.

## Shipped coordination surface

```text
yandex-reaper-thesis run
  thesis-suite-v1
  -> compile existing analyst-experiment-v1 manifest
  -> delegate current collection to the existing 0.2 runner
  -> build an unreviewed intelligence artifact

yandex-reaper-thesis build
  thesis-suite-v1
  + exact current experiment ZIP
  + optional repeatable prior experiment ZIPs
  + optional hash-bound analyst review JSONs
  -> offline deterministic intelligence rebuild

yandex-reaper-thesis verify
  intelligence ZIP
  + exact current experiment ZIP
  + optional repeatable prior experiment ZIPs
  -> package verification
  -> source-bound deterministic rebuild
  -> canonical member-byte comparison
```

`run` intentionally does **not** accept analyst reviews. A P4 review binds an already-existing
semantic-report hash, while a fresh collection produces a new semantic report. The honest flow is:

```text
run unreviewed
-> inspect semantic direct candidates
-> author hash-bound review
-> build the same current experiment ZIP with --review
```

This permits review-only rebuilds without recollecting Yandex data.

## Deterministic source boundary

`build` uses only explicitly supplied immutable experiment ZIPs. It does not query Yandex and does
not consult ambient mutable SQLite state.

For the current artifact it:

1. verifies the existing experiment artifact contract;
2. loads the frozen analyst snapshot / market export;
3. materializes only the packaged `raw/` payload into a temporary directory;
4. replays M1.7 semantic enrichment from that frozen raw evidence;
5. derives P2 traction, P3 anomaly, P4 review/competitor quality and P5 reports/comparison.

Prior experiment inputs are canonicalized by the existing P1 build-identity contract before they are
used by traction or serialized into the final artifact. Reordering repeated `--prior` arguments does
not change the build identity or canonical payload.

## Final artifact identity

The accepted P1 collision-safe identity remains authoritative:

```text
artifacts/intelligence/<suite_id>/<run_id>/<build_input_hash>.zip
```

This intentionally supersedes the earlier one-ZIP-per-run path example. The build hash includes the
canonical current/prior/review bindings, so adding an analyst review creates a new create-only
artifact instead of colliding with the unreviewed build.

No package version bump is performed in P6. `0.2.0` remains authoritative until the P7 real-data and
release gates pass.

## Verification model

P6 uses two distinct verification layers.

### 1. Package verification

`thesis-intelligence-artifact-v1` requires:

- safe normalized relative POSIX member paths;
- no duplicate ZIP paths;
- exact member set agreement with `artifact-manifest.json`;
- sorted manifest entries;
- member size and SHA-256 verification;
- current/prior source artifact hashes and `build_input_hash` in the manifest.

### 2. Source-bound verification

A self-consistent derived ZIP is not sufficient evidence. `verify` therefore rebuilds the canonical
payload from the explicitly supplied frozen current/prior experiment artifacts and packaged review
inputs, then compares:

- suite/run/build identity;
- current/prior artifact hashes and canonical order;
- rebuilt artifact manifest;
- every canonical payload member byte-for-byte.

ZIP container binary equality is not required; canonical member bytes are.

This source-bound verifier closes the intentional trust boundary left by standalone P5 report
validators: a recomputed derived hash cannot substitute for reconstruction from frozen source
evidence.

## Failure isolation / immutability

Source experiment artifacts are opened read-only. Semantic replay copies `raw/` members to temporary
storage. Final packaging occurs in a temporary sibling file and is published only after package and
source-bound verification pass.

On post-processing failure:

- the temporary final artifact is discarded;
- the existing current/prior experiment ZIPs are not rewritten;
- existing 0.2 collection failure behavior remains responsible for preserving its workdir and
  surfacing the existing `yandex-reaper-experiment resume ...` path.

Focused regression coverage includes byte-for-byte source preservation on verification failure.

## Measurement-honesty review

P6 adds no opportunity score, winner, BUILD/WATCH/SKIP recommendation, DAU/revenue estimate, or new
semantic classifier. It only coordinates the evidence contracts already accepted in P1–P5.

Directness remains:

```text
lexical direct_candidate
!= analyst confirmed_direct
!= proven successful game
```

Longitudinal metrics remain based only on explicitly bound frozen prior artifacts. Zero history stays
`no_prior_observation`; P6 does not fabricate velocity from mutable local state.

## Scope rejected during review

Not added:

```text
new collector/runtime
new resume/checkpoint system
scheduler/daemon
ambient history database
automatic query expansion
LLM/embeddings
ranking/opportunity score
dashboard
package version 0.3.0
```

## CI evidence

Pre-final-review gate on P6 implementation:

```text
ruff: PASS
strict mypy: PASS (87 source files)
pytest: 410 passed
coverage: 82.95% (gate >= 80%)
```

A final repository gate is required after the review-driven CLI/test/docs changes before merge.
