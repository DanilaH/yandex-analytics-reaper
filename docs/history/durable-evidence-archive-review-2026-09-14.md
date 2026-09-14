# Durable Evidence Archive — Independent Review — 2026-09-14

**Scope:** independent pre-merge review of the `R0.3.1` durable evidence archive correction for Reaper longitudinal history.

**PR:** `#63` — `Add durable archive for longitudinal Reaper evidence`  
**Review status:** **PASS FOR MERGE; LIVE MIGRATION ACCEPTED AFTER MERGE**

The live GitHub Release publication was deliberately not claimed as tested during the pre-merge review. It has now completed successfully and is recorded separately in [`durable-evidence-archive-live-migration-2026-09-14.md`](durable-evidence-archive-live-migration-2026-09-14.md).

---

## Why this work exists

Reaper 0.3 already treats prior experiment ZIPs as explicit immutable evidence bindings for longitudinal rating deltas. The Sep-13 trend-mechanics sweeps, however, were retained only as GitHub Actions artifacts with `retention-days: 30`.

The four decision-relevant Sep-13 wrapper artifacts expire on 2026-10-13. Losing those bytes would break future replay/delta reconstruction even though the analytical contracts themselves were correct.

This review therefore treats durable archival as a bounded **evidence transport/durability correction**, not as a new analytics system.

---

## Source-of-truth and neighboring docs reviewed

The review re-read the project documentation that can materially conflict with the new boundary:

- `AGENTS.md` — workflow / evidence honesty;
- `README.md` — current capabilities and commands;
- `ARCHITECTURE.md` — raw-first replay, package and persistence boundaries;
- `ROADMAP.md` — R0.3 semantics, sequencing and non-goals;
- `docs/spec/README.md` — living-spec ownership/index;
- `docs/spec/analyst-experiment-runner.md` — immutable experiment publication;
- `docs/spec/thesis-intelligence.md` — current/prior artifact longitudinal semantics;
- `docs/spec/thesis-intelligence-contracts-v1.md` — frozen artifact-binding contracts;
- `docs/spec/thesis-intelligence-build-identity-v1.md` — final intelligence build identity;
- `.gitignore` — runtime `data/*` and `artifacts/*` policy.

Result:

- README, ARCHITECTURE, ROADMAP and the living-spec index needed explicit durable-archive integration and were updated;
- the frozen Thesis Intelligence contracts **must not** be rewritten because the archive changes only where verified ZIP bytes survive, not what a prior artifact means;
- `analyst-experiment-runner.md` remains correct: its create-only local experiment ZIP is still the analytical source artifact; durable Release storage wraps that artifact later rather than changing runner publication semantics.

---

## Evidence checked before implementation

The historical workflow was inspected at the producing commit. It uploaded:

```text
trend-mechanics-result.json
artifacts/
```

with `retention-days: 30`.

Current GitHub metadata for the four Sep-13 artifacts was captured into committed requests with exact:

```text
workflow run id
artifact id
artifact name
created_at
expires_at
source commit SHA
source branch
size
SHA-256 digest
```

Round 2 was also downloaded independently before implementation. The SHA-256 of the exact downloaded Actions ZIP matched GitHub's artifact metadata digest byte-for-byte. Its wrapper contained both the top-level result and inner experiment/intelligence artifacts, confirming that preserving the complete wrapper is stronger than copying only one selected inner ZIP.

A filename/path scan of that real wrapper found no entries containing obvious secret/session markers such as:

```text
cookie
session
secret
.env
token
credential
auth
```

This is consistent with the existing architecture rule that reusable raw cookie values stay only in local session state and are not written into analytical snapshots/SQLite. This scan is a bounded sanity check, not a general content-classification guarantee.

---

## Review findings and repairs

### 1. Initial implementation did not bind enough GitHub provenance

Initial workflow checks covered the artifact name, run id, source SHA, size and digest, but did not compare all committed source metadata.

**Repair:** publication now also fails closed on mismatched:

```text
artifact id
created_at
expires_at
source branch
```

The request therefore binds the historical Actions object more completely before any bytes are published to a Release.

### 2. Archive runs could race each other

Two main-branch/manual archive runs could otherwise create/reconcile the same Release concurrently.

**Repair:** one repository-level workflow concurrency group serializes archive publication with `cancel-in-progress: false`.

### 3. Catalog collisions needed a pre-side-effect gate

A duplicated archive id, Release tag or Actions artifact id across request files could create ambiguous durable identities.

**Repair:** `yandex-reaper-archive validate-catalog` validates the complete committed request set before any Release side effect. Unit coverage includes accepted unique catalogs and rejected collisions.

### 4. Release/asset identifiers were too permissive

Workflow values flow through shell and GitHub CLI publication commands.

**Repair:** archive ids, tags and asset names use a bounded shell-safe vocabulary, the three asset names must be distinct, and the artifact retention window must be chronologically valid.

### 5. Documentation named a non-existent prior flag

The first archive spec referred once to `--prior-artifact`; the actual Thesis CLI contract is repeatable `--prior <zip>`.

**Repair:** the spec now uses the real interface and explicitly keeps Thesis Intelligence semantics unchanged.

### 6. Duplicate-ZIP-member security test emitted avoidable warning noise

The test correctly created a malformed/ambiguous ZIP but left Python's expected duplicate-member `UserWarning` in the full suite.

**Repair:** the warning is explicitly asserted as part of the test setup. The final quality run is warning-free.

### 7. Heavy bytes must not enter Git history

Normal Git history is a bad warehouse for repeated binary CI snapshots because deleting a later path does not remove historical Git objects.

**Decision retained:** Git stores only small request/catalog declarations. GitHub Releases store the byte-preserved Actions wrapper plus generated manifest/checksum. `data/*` and `artifacts/*` remain ignored runtime paths.

---

## Final implementation shape reviewed

```text
committed durable-evidence-archive-request-v1
→ catalog collision preflight
→ exact GitHub Actions metadata reconciliation
→ byte-preserving Actions ZIP download
→ offline SHA-256 + size verification
→ safe ZIP member inventory (path + size + SHA-256)
→ create-only manifest + checksum
→ draft GitHub Release at producing source commit
→ upload missing assets only; never clobber
→ redownload wrapper + manifest + checksum
→ verify against committed request
→ publish Release
```

Later retrieval remains:

```text
Release assets
→ yandex-reaper-archive verify --request ...
→ yandex-reaper-archive extract <exact member>
→ verified local experiment ZIP
→ existing yandex-reaper-thesis --prior <zip>
```

The archive layer cannot turn an invalid inner experiment ZIP into valid evidence. Existing experiment-artifact verification still runs when Thesis Intelligence consumes the extracted ZIP.

---

## Security / failure review

The offline core rejects:

- wrapper SHA/size drift;
- invalid/unreadable ZIPs;
- absolute or `..` member paths;
- ambiguous backslash member paths;
- duplicate ZIP member names;
- manifest/request identity drift;
- missing requested inner members;
- extracted member SHA/size drift;
- create-only manifest replacement with different content.

The GitHub workflow rejects:

- expired Actions artifacts;
- GitHub metadata/request provenance mismatch;
- catalog identity collisions;
- Release target mismatch;
- incomplete published Releases;
- downloaded Release assets that fail request/manifest/checksum verification.

A partial **draft** may only receive missing assets. Existing assets are never overwritten; the whole draft must pass the redownload/verification gate before publication.

No `--clobber` path exists.

---

## Quality gate

Initial CI exposed three Ruff-only findings in the new archive code. They were repaired before acceptance rather than ignored.

Final pre-merge CI:

```text
GitHub Actions run: 34828446524
ruff check .                                  PASS
mypy src                                      PASS — 89 source files
pytest --cov=... --cov-fail-under=80          PASS — 425 tests
warnings                                      0
coverage                                      82.62%
```

The full repository suite passed, not merely the new focused tests.

---

## Live-only verification closure

The following items were intentionally deferred until after merge and are now complete:

1. the main-branch archive workflow created/reconciled all four historical Releases;
2. all three assets for every Release were redownloaded and passed request/manifest/checksum verification;
3. every final Release tag targets its historical producing commit;
4. the ordinary post-merge main CI also passed.

The live acceptance record is:
[`durable-evidence-archive-live-migration-2026-09-14.md`](durable-evidence-archive-live-migration-2026-09-14.md).

GitHub's Release API reports `immutable = false` for the published migration Releases. The contract therefore correctly continues to depend on create-only workflow behavior plus cryptographic verification rather than silently assuming repository-level immutable releases are enabled.

---

## Review decision

**PASS — PRE-MERGE REVIEW AND POST-MERGE LIVE ACCEPTANCE COMPLETE.**

The correction is narrow, evidence-preserving, compatible with the existing 0.3 analytical contracts and does not introduce a scheduler, data lake, remote-history database or new decision engine.

`R0.3.1` may now be marked COMPLETE. Product sequencing remains unchanged: `P2` is still the next primary product path.
