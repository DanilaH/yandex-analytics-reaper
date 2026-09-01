# Analyst Experiment Runner v1.2

## Status

**Target release:** Reaper `0.2.0 — Resumable & Observable Experiments`  
**Workflow version:** `analyst-experiment-v1.2`  
**Manifest schema:** remains `schema_version: 1`  
**Baseline package:** Reaper `0.1.1`  
**Baseline commit reviewed:** `94a30c22a0f69b11fd7deff870f75c0156b3a10e`  
**Spec revision:** independently reviewed and corrected, 2026-09-01

This specification evolves the existing declarative analyst experiment runner after a real market
research sweep exposed three concrete operational blockers:

1. long experiments can exceed an external foreground-shell timeout;
2. the runner emits no useful progress until the entire experiment finishes;
3. a killed experiment cannot reuse expensive completed search work.

The release is not complete until all three capabilities are present:

```text
observable execution
+ deterministic resume
+ bounded exact-query concurrency
```

The purpose of v1.2 is operational: make larger real-world Yandex Games sweeps recoverable,
inspectable, and materially faster without changing analyst-owned evidence semantics.

---

## 1. Product boundary

The runner remains a thin coordinator over existing Reaper boundaries:

```text
versioned manifest
→ exact query collection
→ declared-family comparable sets
→ rich metadata
→ analyst snapshot
→ market export / CSV
→ market features
→ fresh rebuild verification
→ immutable artifact
```

v1.2 adds only the lifecycle capabilities required by the observed failure mode:

```text
persistent run identity
+ exclusive workdir ownership
+ append-only execution trace
+ timings / heartbeat
+ exact-query recovery
+ bounded query workers
+ crash-safe artifact publication
```

It is **not** a workflow framework, scheduler, daemon, distributed worker system, persistent job
server, generic checkpoint system, dashboard, automatic discovery policy, taxonomy classifier, or
opportunity scorer.

The runner knows only the concrete analyst experiment pipeline defined here.

---

## 2. Compatibility and frozen evidence semantics

### 2.1 Manifest schema stays v1

The existing manifest remains valid and unchanged:

```json
{
  "schema_version": 1,
  "experiment_id": "curiosity-payoff-sweep-v1",
  "context": {
    "pages": 3,
    "session_profile": "clean_anonymous",
    "lang": "ru",
    "device": "desktop",
    "platform": "desktop_other"
  },
  "families": [
    {
      "id": "clean-restore",
      "queries": ["clean", "уборка", "реставрация"]
    }
  ]
}
```

Frozen semantics:

- `experiment_id` and family IDs remain lowercase human-readable slugs;
- an exact query may appear in only one family in one manifest;
- the runner never infers, merges, renames, reassigns, or canonicalizes families;
- first declared query = `SEED`;
- remaining declared queries = `OTHER`;
- this ordering is analyst-owned ordinal input, not semantic inference;
- `clean_anonymous` remains the only session profile accepted by this runner contract;
- query-family coherence remains descriptive only;
- query-family union remains a provisional analyst-declared search-derived comparable, not a
  validated canonical market.

Operational worker count is not analyst evidence and MUST NOT be added to manifest schema v1.

### 2.2 Workflow compatibility

The workflow version becomes:

```text
analyst-experiment-v1.2
```

v1.2 is a backward-compatible lifecycle extension of v1.1, not a new experiment model.

The first v1.2 implementation resumes only workdirs whose `run-state.json` explicitly declares:

```text
analyst-experiment-v1.2
```

There is no implicit recovery of v1.1 workdirs because v1.1 did not persist the required recovery
identity.

### 2.3 Package version

The release MUST bump the package version to `0.2.0` in every authoritative version declaration,
including at minimum:

```text
pyproject.toml
src/yandex_analytics_reaper/__init__.py
```

Runtime provenance and tests MUST observe the same package version.

### 2.4 Evidence boundary is unchanged

All existing evidence rules remain mandatory:

```text
raw before interpretation
immutable raw snapshots
derived values traceable to raw
missing != zero
totalGamesCount != canonical competitor count
sponsored != organic
search position != traffic
ratingCount != DAU / revenue
query-family union != validated taxonomy
no opaque opportunity score
```

Resume, workers, retries, logs, and timings MUST NOT weaken these rules.

---

## 3. CLI contract

v1.2 exposes two commands.

### 3.1 New run

```bash
yandex-reaper-experiment run path/to/experiment.json
```

Operational override:

```bash
yandex-reaper-experiment run path/to/experiment.json --workers 1
```

### 3.2 Resume

```bash
yandex-reaper-experiment resume \
  artifacts/work/<experiment_id>/<run_id>
```

Operational override:

```bash
yandex-reaper-experiment resume \
  artifacts/work/<experiment_id>/<run_id> \
  --workers 1
```

### 3.3 Worker option

`--workers` is operational configuration, not experiment input.

v1.2 contract:

```text
default = 4
minimum = 1
maximum = 4
```

The conservative ceiling is intentional. v1.2 MUST NOT expose arbitrary 10/20/50 worker counts.

A lower value exists for source-stability diagnostics and explicit fallback. The runner MUST NOT
silently auto-fallback from four workers to one after a failure: preserve the failed run and let
the operator explicitly resume with a lower value.

### 3.4 Exit behavior

Expected process exits:

- `0` — verified success;
- `1` — runtime / experiment failure;
- `2` — CLI parsing / usage failure.

A runtime failure reports a resume command only when the target workdir has a valid v1.2 recovery
identity.

---

## 4. Run identity and paths

### 4.1 Identities

`experiment_id` identifies the analyst-declared experiment definition.

Every new execution receives one generated UTC `run_id`, for example:

```text
20260901T001234Z
```

A same-second collision uses the existing deterministic suffix behavior rather than overwriting an
existing run.

### 4.2 Paths

Active state:

```text
artifacts/work/<experiment_id>/<run_id>/
```

Successful immutable artifact:

```text
artifacts/exports/<experiment_id>/<run_id>.zip
```

The final export is create-only.

### 4.3 Success and failure lifetime

A successful run deletes the workdir only after:

1. downstream verification passes;
2. artifact payload is frozen;
3. temporary ZIP is verified;
4. final ZIP identity/hash is known;
5. final ZIP has been published safely;
6. success result can be returned.

Any failed run/resume after durable initialization preserves the workdir.

---

## 5. Exclusive workdir execution ownership

Resume semantics are unsafe if two processes operate the same workdir simultaneously. One process
could otherwise misclassify the other process's active `RUNNING` probe as stale.

Therefore exactly one runner process may own a workdir at a time.

### 5.1 Required lock

Every `run` and `resume` MUST hold an exclusive process-owned workdir lock for the active lifecycle.

Suggested path:

```text
<workdir>/run.lock
```

The mechanism MUST:

- fail closed when another live process owns the workdir;
- be released automatically when the process exits or is killed by the OS;
- work for the supported local platforms;
- not rely on a persistent PID/marker file alone to determine liveness.

An OS advisory file lock or equivalent process-held primitive is appropriate.

The lock file itself is operational state and is excluded from the final artifact.

### 5.2 Ordering

On resume, acquire exclusive ownership **before**:

- declaring any pre-existing `RUNNING` probe stale;
- modifying logs;
- scheduling source work;
- rebuilding derived output.

No time-based stale threshold is required. A pre-existing `RUNNING` probe is abandoned for recovery
because the new process has exclusive ownership of the preserved workdir, not because it is N
minutes old.

---

## 6. Persistent `run-state.json`

### 6.1 Purpose

v1.2 requires an early durable recovery identity:

```text
<workdir>/run-state.json
```

It is created after workdir allocation and verbatim manifest copy, before the first network
request.

### 6.2 Minimum contract

```json
{
  "schema_version": 1,
  "experiment_id": "mystery-unboxing-collection-sweep-v1",
  "run_id": "20260901T001234Z",
  "started_at": "2026-09-01T00:12:34.123456Z",
  "manifest_sha256": "<64-char lowercase sha256>",
  "workflow_version": "analyst-experiment-v1.2"
}
```

Recommended model properties:

- frozen;
- `extra="forbid"`;
- timezone-aware UTC timestamp validation;
- lowercase SHA-256 validation;
- validated experiment/run identity.

### 6.3 Immutable identity, not live progress

`run-state.json` MUST NOT be rewritten to track:

- current stage;
- current worker;
- completed query count;
- retry count;
- heartbeat;
- resume count.

Progress belongs in append-only logs and persisted evidence. Keeping recovery identity immutable
avoids turning one small requirement into a fragile mutable state machine.

### 6.4 Durable creation

Creation MUST be fail-closed and crash-conscious. A temporary sibling file followed by an atomic
publish is preferred.

Once the runner reports the workdir as initialized, a complete parseable `run-state.json` MUST
exist.

An interruption before durable state creation may leave an uninitialized orphan directory. Such a
directory is not resumable and `resume` MUST reject it rather than guessing its identity.

### 6.5 Recovery authority

On resume, `run-state.json` defines the original:

- `experiment_id`;
- `run_id`;
- `started_at`;
- manifest hash;
- workflow version.

Resume MUST NOT create a new semantic run identity.

---

## 7. Verbatim manifest persistence and resume preflight

A new run copies the exact input bytes to:

```text
input/manifest.json
```

The SHA-256 of those exact bytes is persisted in `run-state.json`.

Resume uses the workdir-owned manifest; the original external manifest path is not required.

Before any source network I/O, resume MUST validate:

1. target exists and is a directory;
2. target resolves inside the repository's expected
   `artifacts/work/<experiment_id>/<run_id>` hierarchy;
3. exclusive workdir lock is held;
4. `run-state.json` exists and parses;
5. `input/manifest.json` exists;
6. manifest hash equals `run_state.manifest_sha256`;
7. manifest validates as schema v1;
8. manifest `experiment_id` equals run-state `experiment_id`;
9. path experiment/run components equal run-state identity;
10. workflow version is supported;
11. original `run_id` is reused;
12. original `started_at` is reused.

Any mismatch fails closed before network work.

---

## 8. Why original `started_at` is mandatory

`QueryFamilyVersion` is immutable and its persisted content includes `created_at`.

Recreating the same family on resume with a new `datetime.now()` can therefore conflict with the
already persisted `(family_id, version)` even when the analyst manifest is unchanged.

Every query family reconstructed during resume MUST use:

```text
created_at = run_state.started_at
```

This requirement is specific to query-family identity.

An already persisted comparable set retains its own original `created_at`; a newly built comparable
uses its normal construction timestamp. Do not rewrite existing immutable comparable metadata.

---

## 9. Execution lifecycle

### 9.1 New run

```text
validate manifest
→ allocate workdir
→ acquire workdir ownership
→ copy manifest verbatim
→ create immutable run-state
→ initialize append-only logs
→ initialize stores
→ persist declared query families
→ collect exact queries with bounded workers
→ build family comparables
→ family coherence
→ rich metadata
→ rebuild snapshot/export/CSV/features
→ fresh rebuild verification
→ execution timings/summary
→ artifact manifest
→ temporary ZIP
→ verify temporary ZIP
→ hash temporary ZIP
→ atomically publish final ZIP create-only
→ success cleanup
```

### 9.2 Resume

```text
resolve workdir
→ acquire workdir ownership
→ validate run-state + manifest identity
→ detect already-published terminal success if present
→ append resume log boundary
→ initialize existing stores
→ persist/validate original query families using original started_at
→ recover exact selected search evidence
→ collect missing/incomplete exact queries
→ reuse/build comparables
→ clear stale derived outputs
→ rebuild downstream
→ verify
→ package safely
→ success cleanup
```

Downstream stages MUST NOT begin until the complete exact-query cohort required by the manifest is
available.

---

## 10. Search recovery atomicity

The recovery atomic unit is:

> **one whole exact query run**

Not one page.

Example:

```text
query A: page 1 ✓ page 2 ✓ page 3 ✓ COMPLETED
query B: page 1 ✓ page 2 ✓ hard kill
```

Resume:

```text
query A → reusable if validated
query B → rerun from page 1
```

The runner MUST NOT continue query B directly from page 3.

Rationale:

- pagination token continuity;
- fresh session semantics;
- simple deterministic recovery;
- bounded ambiguity.

With four workers, a hard kill may discard up to four in-flight exact-query units while preserving
all proven completed units.

---

## 11. Recovery selection: existing comparables are authoritative

A subtle but important rule: when an immutable family comparable already exists, recovery MUST NOT
first choose a newer duplicate completed query run and then declare the existing comparable a
conflict.

### 11.1 Existing comparable first

For each family, recovery first checks the exact expected comparable identity:

```text
set_id  = <experiment_id>--<family_id>
version = 1
```

If it exists:

1. load it through `SQLiteComparableSetStore`;
2. validate its query-family identity and exact declared query order;
3. validate every referenced probe run is still valid completed search evidence;
4. replay/rebuild the comparable from its **own referenced run IDs**, using its original
   `created_at`;
5. require the rebuilt value to equal the stored immutable comparable exactly.

If this succeeds, those referenced probe run IDs are the authoritative selected runs for that
family during recovery.

Any newer duplicate completed probe runs remain unselected forensic history.

If the existing comparable cannot be validated/replayed exactly, recovery fails closed. It MUST
NOT silently overwrite it or invent a new comparable version.

### 11.2 No existing comparable

Only when the expected family comparable does not exist does recovery discover reusable completed
probe candidates per exact query and select one deterministically.

This ordering prevents false immutable conflicts after crashes that occurred after comparable
persistence but before final packaging.

---

## 12. Reusable exact-query evidence

### 12.1 Required store lookup API

The current probe store exposes direct `get_run(id)` but recovery requires bounded discovery by
structured identity.

v1.2 MUST add a narrow read API to the probe storage boundary, for example conceptually:

```text
find search runs by:
source_id
request_key
kind
context
query_text
requested_page_limit
```

The exact Python signature is implementation-owned, but the coordinator MUST NOT embed ad-hoc raw
SQL against `probe_runs` merely to implement resume.

The lookup is additive and does not by itself require a schema migration. Add an index only if
measurement shows the existing run index is inadequate.

### 12.2 Reuse criteria

A candidate may be reused only if structured persisted evidence proves:

```text
source_id             == "yandex_public"
request_key           == "catalogue.search"
kind                  == SEARCH
query_text            == exact manifest query
effective ProbeContext == expected clean_anonymous context
requested page limit  == manifest.context.pages
status                == COMPLETED
completed_at          != null
persisted page chain  is valid
raw snapshot replay   is valid
termination           == source exhausted OR requested limit reached
```

The expected effective clean-anonymous context includes the existing session normalization:

```text
session_instance_id = null
cookie_state_hash    = null
profile_age_days     = 0
```

### 12.3 Reuse validation MUST share comparable invariants

The current comparable builder already performs strong validation/replay of completed search runs:

- exact source/request/kind/query/context/page limit;
- contiguous page chain;
- correct exhaustion/limit termination;
- raw metadata/body replay;
- content hash and HTTP success;
- exact request context;
- parser replay;
- reconstructed `ProbePage` equality.

v1.2 MUST factor or otherwise reuse those same single-run validation invariants for recovery.

Do not implement a weaker second validator in the coordinator that checks only database status and
page count.

### 12.4 Never reusable

These statuses are never reusable:

```text
RUNNING
PARTIAL
FAILED
```

Even a `RUNNING` run that happens to have the requested number of raw pages is not reusable because
terminal completion was never durably established.

### 12.5 Multiple completed candidates without a comparable

When no existing family comparable anchors selection and several fully validated `COMPLETED`
candidates exist for one exact query, choose deterministically:

1. latest persisted `completed_at`;
2. stable probe run ID as final tie-breaker.

The selection rule applies only after full reuse validation.

---

## 13. Stale `RUNNING` evidence

A hard kill can leave a probe run in `RUNNING` forever.

After resume has exclusive workdir ownership, every pre-existing `RUNNING` candidate matching the
recovery query is considered abandoned for recovery purposes.

Required behavior:

- never bind it into a comparable;
- never infer completion from available raw pages;
- do not need to mutate/delete it;
- preserve it for forensic history;
- emit an explicit stale-probe event/log line;
- rerun the exact query from page 1 unless an authoritative reusable run is already selected.

Example:

```text
! stale probe ignored  query="что внутри"  pages=2/3  probe=probe:...
```

Stale evidence may remain in `market.sqlite3` and `raw/` as unselected forensic history. The
selected comparable cohort, not the mere presence of files/rows, defines analytical membership.

---

## 14. Search concurrency model

### 14.1 Scope

v1.2 parallelizes only independent exact queries.

Allowed:

```text
W1: query A p1 → p2 → p3
W2: query B p1 → p2 → p3
W3: query C p1 → p2 → p3
W4: query D p1 → p2 → p3
```

Forbidden:

```text
query A p1 ┐
query A p2 ├─ parallel
query A p3 ┘
```

Pagination within one exact query remains strictly sequential.

### 14.2 Global stable query indexing

Queries SHOULD be scheduled across the whole manifest rather than forcing workers to idle at family
boundaries.

Flattened manifest order defines stable indices:

```text
01/36
02/36
...
36/36
```

Worker scheduling may alter completion order. It MUST NOT alter analyst-visible family/query order
in comparables, coherence reports, timing report ordering, or downstream artifacts.

### 14.3 Bounded scheduler

At most `workers` exact-query units may be active simultaneously.

The scheduler SHOULD maintain only a bounded active set. There is no nested page pool, no nested
rich-metadata pool, and no concurrent downstream pipeline.

### 14.4 Session isolation

Each exact-query attempt uses its own search session/client lifecycle under the existing
`clean_anonymous` contract.

Workers MUST NOT share mutable pagination tokens, cookie jars, or HTTP client state.

### 14.5 Worker identity

`W1`–`W4` are runtime labels only. They are not evidence identity and do not enter the manifest,
query family, or taxonomy.

---

## 15. Determinism under concurrency

Concurrency changes wall-clock scheduling, not semantic ordering.

The following MUST be assembled in manifest order, never future-completion order:

- family list;
- query list within a family;
- selected run-ID list passed to comparable construction;
- query diagnostics;
- coherence report ordering;
- comparable-set ordering downstream;
- timing report query rows.

A real live source can change between requests, so v1.2 does not claim that independent live
`workers=1` and `workers=4` runs at different times are byte-identical.

With a deterministic mocked source, however, one-worker and four-worker executions MUST produce
structurally equivalent selected evidence and deterministic downstream outputs.

---

## 16. Concurrency and persistence safety

### 16.1 Prohibited implementation

Do not blindly wrap the current sequential family/query loop in `ThreadPoolExecutor(4)` while
leaving shared SQLite behavior unreviewed.

The search path touches shared:

- probe-run SQLite storage;
- schema-drift SQLite storage;
- raw snapshot filesystem storage.

SQLite currently uses separate connections, `busy_timeout=5000`, and no WAL. v1.2 MUST NOT depend
on accidental concurrent-writer behavior.

### 16.2 Required v1.2 strategy

Preferred and default architecture:

> **concurrent network waits + serialized SQLite-affecting search persistence**

Requirements:

- independent HTTP waits may overlap;
- page chain in one query stays sequential;
- shared SQLite operations reached from search workers use one application-level serialization
  boundary (lock or equivalent);
- the lock MUST NOT cover the remote HTTP request itself;
- schema observation/parser-failure persistence and probe create/page/finalization operations must
  obey the same safety boundary;
- downstream remains serial.

Reads used by active worker finalization may share the same boundary when doing so simplifies
correctness. Do not optimize lock granularity before measurement.

Enabling WAL is not required and is not a substitute for proving the actual access pattern safe.

If implementation intentionally chooses concurrent SQLite writes instead, it must include focused
proof/tests for every affected store. Without that proof, serialized persistence is mandatory.

### 16.3 Raw snapshot concurrency

Raw snapshot writes may occur concurrently because their generated paths are unique.

v1.2 does **not** require a broad filesystem-transaction rewrite or claim that a multi-file raw
snapshot directory is magically atomic across `SIGKILL`.

Required properties are narrower:

- generated snapshot paths remain collision-safe;
- raw-before-interpretation semantics remain unchanged;
- a hard kill may leave an orphan/incomplete raw directory;
- an orphan raw directory with no valid persisted completed probe linkage is never reusable
  evidence;
- final replay of selected evidence still verifies metadata/body integrity.

---

## 17. Failure semantics with active workers

If one query reaches a non-retriable failure or exhausts transport attempts:

1. emit exact structured failure context;
2. stop scheduling new pending queries;
3. cancel queued-but-not-started work when safely possible;
4. do not forcibly terminate already-running exact-query units;
5. let active sibling units finish/fail naturally;
6. preserve siblings that durably reach valid `COMPLETED`;
7. fail the `search_collection` stage;
8. do not build incomplete family comparables;
9. do not start downstream stages;
10. preserve the workdir.

Completed sibling work becomes valid future resume material.

A family comparable MUST NOT be built from a subset just because another worker failed.

---

## 18. Existing retry boundary remains frozen

Maximum attempts:

```text
3 total attempts
```

Retry only:

```text
httpx.ConnectTimeout
httpx.ReadTimeout
httpx.ConnectError
```

Do not retry semantic/source failures such as:

- HTTP/source error after a response exists;
- breaking schema drift;
- parser failure;
- normalization failure;
- persisted partial semantic result.

Existing delay policy remains:

```text
after attempt 1 failure → 1s
after attempt 2 failure → 2s
attempt 3 failure       → terminal
```

Each retry emits query, worker, failed attempt, next attempt, error type, delay, and elapsed time.

A transport retry may create a separate persisted probe attempt; recovery selection rules handle
those attempts explicitly.

---

## 19. Comparable-set resume

Comparable sets remain immutable.

### 19.1 Existing comparable

Use the authoritative existing-comparable algorithm in Section 11.

The strongest validation is exact replay/rebuild using the comparable's own selected run IDs and
its original `created_at`, followed by equality with the stored object.

### 19.2 Missing comparable

When no exact comparable exists and every required query has one selected valid completed run:

- build one `yandex_search_union_v1` comparable using selected run IDs in declared query order;
- persist it once at the existing set ID/version.

### 19.3 Conflict

Any immutable conflict fails closed.

Do not overwrite.

Do not silently bump comparable version merely to escape the conflict.

---

## 20. Downstream recovery strategy

v1.2 intentionally does **not** checkpoint/resume:

- family coherence generation;
- rich metadata batch progress;
- analyst snapshot;
- market export;
- CSV;
- market features;
- verification;
- artifact manifest;
- ZIP packaging.

Once required search/comparable evidence is complete, those stages are rebuilt.

Before a resumed downstream rebuild, the runner MUST clear/recreate its generated derived-output
areas sufficiently to prevent partially written files from an interrupted invocation from being
mistaken for final outputs. This applies to generated report/CSV/package-temporary files, not to:

```text
input/
raw/
market.sqlite3
logs/
run-state.json
```

Principle:

```text
expensive source evidence → narrow recovery
cheap deterministic derivation → rebuild cleanly
```

Do not add a generic stage checkpoint state machine.

---

## 21. Rich metadata in v1.2

Rich metadata preserves existing batching:

```text
<= 100 app IDs per request
```

and the existing transport retry boundary.

### 21.1 Resume

Exact rich-batch resume is **not required** in v1.2.

After search/comparables are recovered, rich metadata may be recollected from the beginning for the
current comparable union.

### 21.2 Concurrency

Rich metadata remains sequential in v1.2.

Do not parallelize it merely because search queries now have workers.

---

## 22. Observability architecture

v1.2 introduces one small structured execution-event boundary used by:

```text
console renderer
run.log renderer
events.jsonl writer
heartbeat active-state view
failure summary
timing aggregation
```

Coordinator/collection components SHOULD emit structured events rather than ad-hoc `print()` calls
spread throughout the codebase.

This is a runner-specific event emitter, not a general telemetry framework.

---

## 23. Persistent execution logs

Active/failed workdir contains:

```text
logs/run.log
logs/events.jsonl
```

### 23.1 `run.log`

Human-readable append-only trace including:

- run/resume boundaries;
- stage start/end;
- query start/end/reuse;
- page completion;
- retries;
- worker identity;
- stale probe ignored;
- heartbeat;
- terminal failure.

### 23.2 `events.jsonl`

Machine-readable event stream: one JSON object per complete line.

### 23.3 Resume append behavior

Resume never truncates prior execution history.

If a hard kill left `events.jsonl` without a trailing newline:

1. preserve the incomplete trailing bytes;
2. append a newline boundary before writing the next JSON object;
3. emit `resume_started` as the first new complete event.

This means an interrupted-and-resumed event file may contain **one preserved malformed line per hard
interruption**. Consumers must parse line-by-line and tolerate malformed interrupted fragments;
recovery decisions MUST NOT depend on event-log completeness.

A clean handled run/failure produces fully parseable complete JSONL records.

This rule avoids both truncating forensic bytes and concatenating a new valid JSON object onto a
partial old object.

### 23.4 Flush

Important events MUST be flushed promptly:

- initialization;
- stage start/end;
- query start/end/reuse;
- page completion;
- retry;
- stale probe ignored;
- terminal failure.

Logs are observability state, not evidence authority.

Recovery authority remains:

```text
run-state identity
+ input manifest
+ persisted evidence/stores
+ validated immutable comparables
```

---

## 24. Event contract

Every event SHOULD contain a base envelope:

```json
{
  "ts": "2026-09-01T00:12:45.123456Z",
  "event": "query_completed",
  "stage": "search_collection",
  "invocation_elapsed_s": 11.42
}
```

Use UTC wall clock for timestamps and a monotonic clock for durations.

Optional fields when applicable:

```json
{
  "worker": 2,
  "family_id": "unboxing",
  "query": "распаковка",
  "query_index": 2,
  "query_total": 36,
  "page": 3,
  "page_limit": 3,
  "attempt": 1,
  "max_attempts": 3,
  "probe_run_id": "probe:...",
  "listings": 71,
  "error_type": "httpx.ReadTimeout",
  "error": "...",
  "retry_delay_s": 1.0
}
```

Required event families:

```text
run_started
resume_started
stage_started
stage_completed
query_reused
stale_probe_ignored
query_started
page_completed
query_retry
query_completed
query_failed
rich_batch_started
rich_batch_completed
heartbeat
experiment_failed
experiment_completed
```

Small additional events are allowed when useful. Do not create an unbounded event taxonomy.

---

## 25. Console UX

### 25.1 Non-interactive first

Captured agent-shell output is first-class:

- append-only lines;
- no spinner dependency;
- no `\r` cursor redraw;
- no screen clear;
- no assumption about TTY width.

A richer TTY renderer is not required for v1.2.

### 25.2 Startup example

```text
Yandex Analytics Reaper
experiment : mystery-unboxing-collection-sweep-v1
run        : 20260901T001234Z
queries    : 36
families   : 15
pages      : 3
workers    : 4

✓ manifest validated
✓ workdir initialized
▶ search collection  0/36
```

### 25.3 Worker example

```text
W1 ▶ [01/36] unboxing
W2 ▶ [02/36] распаковка
W3 ▶ [03/36] surprise
W4 ▶ [04/36] сюрприз

W2 ✓ [02/36] распаковка  3 pages · 71 listings · 4.2s
W2 ▶ [05/36] mystery box

W3 ! [03/36] surprise  ReadTimeout · retry 1/2 · delay 1s
```

### 25.4 Resume example

```text
RESUME
run        : 20260901T001234Z
workers    : 4
selected   : 21/36

✓ reuse [01/36] unboxing
✓ reuse [02/36] распаковка
...
! stale probe ignored [22/36] что внутри  pages=2/3
W1 ▶ rerun [22/36] что внутри
```

### 25.5 Final stages example

```text
✓ search collection       36/36 · 02:41
✓ comparable sets         15/15 · 1.8s
✓ family coherence        15/15 · 0.7s

▶ rich metadata           0/612
  batch 1/7 ✓ 100/100
  batch 2/7 ✓ 100/100
✓ rich metadata           612/612 · 8.4s

▶ analyst snapshot
✓ analyst snapshot        2.0s
▶ market export
✓ market export           5.7s
▶ market features
✓ market features         1.4s
▶ evidence verification
✓ evidence verification   8.2s
▶ packaging
✓ package verified
✓ artifact published

PASS
artifact: artifacts/exports/.../...zip
```

Exact spacing/glyphs are not the contract. Information content is.

---

## 26. Heartbeat

Default heartbeat interval:

```text
15 seconds
```

This is an implementation constant, not a manifest field.

Emit a heartbeat only when no meaningful progress/completion line has been emitted during the
interval.

Example:

```text
progress 17/36 · invocation elapsed 00:01:42
active W1 mystery-box p2/3 · W2 редкость p1/3 · W3 collection p3/3 · W4 lucky block p1/3
```

Heartbeat must be low-volume, append-only, thread-safe, and excluded from evidence decisions.

Tests use an injected/fake monotonic clock instead of sleeping real 15-second intervals.

---

## 27. Timing semantics

v1.2 measures performance but must not fabricate timings lost across a hard process kill.

### 27.1 Clocks

Use:

- UTC wall clock for provenance timestamps;
- monotonic clock for elapsed durations.

### 27.2 Required stage timings for the successful invocation

Measure at minimum:

```text
manifest / resume validation
workdir initialization when applicable
search recovery + collection
comparable validation/build
family coherence
rich metadata
analyst snapshot
market export
CSV export
market features
evidence verification
artifact-manifest preparation
temporary ZIP write
temporary ZIP verification
final ZIP hash / publication
total successful invocation
```

### 27.3 Unit timings

Measure during the active invocation:

- per collected exact query;
- per completed page;
- retry delay;
- per rich-metadata batch;
- reusable-query validation time when useful.

### 27.4 `reports/execution-timings.json`

Before packaging, freeze timings that can be represented without self-reference:

```text
reports/execution-timings.json
```

Minimum model:

```json
{
  "spec_version": "analyst-experiment-timings-v1",
  "experiment_id": "...",
  "run_id": "...",
  "invocation_mode": "resume",
  "query_workers": 4,
  "stages": {},
  "queries": [],
  "rich_batches": []
}
```

Query entries preserve manifest order and indicate at least:

```text
action = collected | reused
```

A reused query MUST NOT be assigned invented network duration from a previous process.

### 27.5 Interrupted invocation boundary

If an earlier invocation was killed, its in-memory monotonic timings are gone. v1.2 MUST NOT build
a log-analytics subsystem just to reconstruct them.

Therefore the packaged timing report describes the **final successful invocation**. Earlier
invocation traces remain available in preserved execution logs while the workdir exists.

The execution summary's original `started_at` remains lifecycle provenance and may span downtime
between invocations; it is not labeled as active CPU/network runtime.

### 27.6 Packaging self-reference

The exact final publication/hash duration cannot be inserted back into the same immutable ZIP after
that ZIP is frozen.

Pre-publication timing data belongs in `execution-timings.json`; final publication/hash timing is
shown in console/`run.log` and the returned result. Do not introduce a two-pass self-referential
archive scheme.

---

## 28. Failure summary

A handled failure prints explicit context.

Example:

```text
✗ EXPERIMENT FAILED

stage       : search_collection
worker      : W3
query       : "surprise"
query       : 3/36
family      : surprise
page        : 2/3
attempt     : 3/3
error       : httpx.ReadTimeout
elapsed     : 00:01:43

last raw snapshot:
raw/yandex_public/...

workdir preserved:
artifacts/work/mystery-unboxing-collection-sweep-v1/20260901T001234Z

resume:
yandex-reaper-experiment resume artifacts/work/mystery-unboxing-collection-sweep-v1/20260901T001234Z
```

Unknown fields are omitted or explicitly unknown; never invent page/query context.

A resume command is printed only when `run-state.json` and workdir identity are valid enough to make
the command meaningful.

---

## 29. Execution summary v1.2

`execution-summary.json` remains part of the final package.

Existing provenance remains, with:

```text
workflow_version = analyst-experiment-v1.2
```

v1.2 additionally records at least:

```text
final_invocation_mode       = run | resume
final_invocation_started_at
final_invocation_workers
was_resumed
reused_query_count
collected_query_count
verifier_status
```

`started_at` remains the original lifecycle start from `run-state.json`.

`final_invocation_workers` is operational provenance for the successful invocation, not analyst
evidence.

Do not add a generic persistent invocation-history model in v1.2.

---

## 30. Final artifact payload: explicit allowlist

The current v1.1 packager recursively includes every file in the workdir. That behavior is no
longer safe once v1.2 adds logs, locks, run-state, and temporary packaging files.

v1.2 MUST replace implicit `workdir.rglob('*')` packaging with one shared explicit artifact-payload
selector used by both artifact-manifest construction and ZIP writing.

### 30.1 Required payload

The final ZIP contains at minimum:

```text
input/manifest.json
raw/**
market.sqlite3
reports/analyst-snapshot.json
reports/market-export.json
reports/market-features.json
reports/family-coherence.json
reports/verification.json
reports/execution-timings.json
csv/**
execution-summary.json
artifact-manifest.json
```

### 30.2 Explicitly operational / excluded

These are workdir operational state and MUST NOT be included merely because they exist:

```text
run-state.json
run.lock
logs/**
sessions/**
package temporary files
SQLite transient journal/shm/wal files if any
other undeclared scratch files
```

### 30.3 One selector, two consumers

There MUST be one authoritative payload-selection function/policy.

Conceptually:

```text
artifact payload paths
→ build artifact-manifest hashes
→ package exactly those same paths
+ artifact-manifest.json
```

The manifest builder and ZIP writer MUST NOT independently rediscover files with separate recursive
rules.

Unknown scratch files are not silently packaged.

### 30.4 Recovery history inside evidence payload

`raw/**` and `market.sqlite3` may legitimately contain unselected failed/stale probe history from an
interrupted invocation. That is forensic evidence, not comparable membership.

The selected comparable run IDs remain the authoritative analytical cohort.

---

## 31. Crash-safe artifact publication

A hard kill while writing directly to the final export path can leave a partial `<run_id>.zip` that
blocks future create-only resume. v1.2 MUST close this failure window.

### 31.1 Required sequence

Finalization is normative:

```text
freeze artifact payload
→ write artifact-manifest.json
→ build temporary ZIP at an owned temporary path
→ verify temporary ZIP completely
→ compare verified manifest with expected manifest
→ hash temporary ZIP
→ publish final artifacts/exports/<experiment>/<run_id>.zip atomically/create-only
→ report success
```

The temporary path must not be selected into the final artifact payload.

### 31.2 Final path is never a work-in-progress file

Do not stream ZIP bytes directly into the final export path.

The final path becomes visible only when a fully verified artifact is ready to publish.

Publication MUST preserve create-only semantics; no silent overwrite.

### 31.3 Resume after publication but before cleanup

A process can still die after final artifact publication but before workdir cleanup/success output.

On resume, while holding the workdir lock:

1. if the final ZIP does not exist, continue normal recovery;
2. if it exists, verify it fully against expected experiment/run identity;
3. when workdir `artifact-manifest.json` is available, require equality with packaged manifest;
4. recompute final ZIP hash;
5. if fully valid, treat this as terminal-success recovery and finish cleanup/return success;
6. if invalid or mismatched, fail closed and do not overwrite it.

Owned stale temporary package files may be discarded/rebuilt after the workdir lock is acquired.

---

## 32. Fresh rebuild verification

v1.2 preserves the v1.1 verification principle.

After collection and derivation, freshly rebuild:

```text
snapshot
→ market export
→ market features
```

and require exact equality/content-hash agreement under the existing verification contract.

No failed/partial/stale probe evidence may silently enter the selected comparable cohort.

A resumed artifact may contain additional forensic raw/DB history but must satisfy the same final
artifact **contract** and selected-evidence verification as a normal successful v1.2 run.

---

## 33. Cleanup

### Success

Only after verified final artifact publication and final hash:

```text
remove workdir
```

### Failure

On any failure after durable workdir initialization:

```text
preserve workdir
```

including failures during:

- concurrent search;
- resume recovery;
- downstream rebuild;
- verification;
- temp packaging;
- package verification;
- publication.

---

## 34. Performance and source-stability claims

A large target sweep can involve:

```text
36 exact queries × 3 pages
= up to 108 search HTTP requests
```

Sequential network collection is the leading suspected bottleneck, but v1.2 must measure it.

Allowed release statement:

> exact-query collection is bounded-concurrent with a default of four workers.

Not allowed without measured evidence:

> four times faster.

The four-worker ceiling is deliberately conservative. v1.2 does not add adaptive high-concurrency
probing, anti-bot evasion, proxy rotation, distributed collection, or automatic worker scaling.

If the source rejects four-worker collection, preserve the run and allow explicit resume with a
lower worker count.

---

## 35. Thread-safe observability

Multiple workers MUST NOT corrupt output.

The central event emitter serializes writes to:

- stdout renderer;
- `run.log`;
- `events.jsonl`;
- active-worker state used by heartbeat.

One JSONL event is written as one coherent record.

Worker execution code SHOULD report structured events through the central emitter rather than
printing directly.

---

## 36. Instrumentation boundary

Page-level observability should not duplicate Yandex pagination logic.

The existing paginated collector already owns page index, raw capture, schema observation, parser
work, `ProbePage` creation, and terminal run status.

v1.2 SHOULD add a narrow observer/callback/event hook or equivalent adapter at that boundary to
expose:

- query start/end;
- page start/completion where useful;
- page index/limit;
- raw snapshot reference;
- listing count;
- failure context.

Do not parse exception strings to discover page numbers.

Do not fork a second pagination implementation for observability.

The same refactor may introduce lock-aware storage adapters required by Section 16.

---

## 37. Normative resume algorithm

```text
1. Resolve repository root and workdir.
2. Acquire exclusive workdir ownership.
3. Read/validate run-state.json.
4. Read input/manifest.json and verify exact SHA.
5. Restore original experiment_id, run_id, started_at.
6. If a final ZIP already exists, perform terminal-success recovery check.
7. Repair only the JSONL line boundary if a prior hard kill left a partial tail;
   append resume_started; never truncate forensic bytes.
8. Initialize existing raw/SQLite stores.
9. Recreate and persist/validate every QueryFamilyVersion with original started_at.
10. For each family in manifest order:
    a. load expected comparable if it exists;
    b. if present, replay/rebuild it from its own run IDs and require exact equality;
    c. mark those run IDs authoritative for that family;
    d. if absent, discover fully validated COMPLETED candidates per query;
    e. select deterministic candidates only where no comparable anchors selection;
    f. mark remaining queries pending.
11. Emit stale_probe_ignored for matching abandoned RUNNING attempts as applicable.
12. Schedule pending exact queries with bounded workers.
13. On search success, assemble one selected run ID per manifest query in manifest order.
14. Reuse validated existing comparables; build missing comparables once.
15. Rebuild family coherence.
16. Recompute comparable union.
17. Clear stale derived report/CSV/package-temporary outputs.
18. Recollect rich metadata.
19. Rebuild snapshot/export/CSV/features.
20. Fresh-rebuild verification.
21. Freeze successful-invocation timing report and execution summary.
22. Build artifact manifest from explicit payload selector.
23. Build and verify temporary ZIP.
24. Hash and publish final ZIP create-only.
25. Delete workdir only after success.
```

This is deliberately pipeline-specific, not a generic recovery engine.

---

## 38. Normative new-run algorithm

```text
1. Read/validate manifest before source network I/O.
2. Resolve repository root.
3. Allocate unique run_id/workdir.
4. Acquire workdir ownership.
5. Persist verbatim manifest.
6. Persist immutable run-state.
7. Initialize logs.
8. Initialize stores.
9. Persist all query families serially with started_at.
10. Flatten exact queries into stable manifest order.
11. Schedule up to four exact-query units globally.
12. Keep pages sequential inside each query.
13. Keep SQLite-affecting search persistence serialized while network waits overlap.
14. Assemble selected run IDs in manifest order.
15. Build comparables serially in manifest family order.
16. Continue serial downstream pipeline.
17. Verify and publish artifact through the crash-safe sequence.
```

---

## 39. Focused test plan

The implementation needs strong lifecycle tests, but the spec does not require dozens of nearly
duplicate test functions. Parametrize aggressively and keep tests centered on the actual failure
modes.

### A. Durable identity and ownership

1. `run-state.json` exists before first mocked source request and matches verbatim manifest SHA.
2. resume rejects manifest/hash/workflow/path identity mismatch before source I/O.
3. original `run_id` and `started_at` survive resume and query-family persistence.
4. second live process cannot operate the same workdir concurrently.
5. abandoned workdir lock is automatically releasable after process death semantics are simulated
   at the lock abstraction boundary.

### B. Exact-query recovery

6. valid completed query is reused with zero new source request.
7. `PARTIAL`, `FAILED`, and stale `RUNNING` queries rerun from page 1.
8. `RUNNING` with all expected pages is still not reused.
9. corrupted/missing raw page prevents reuse.
10. multiple valid completed candidates select deterministically only when no comparable anchors
    the family.
11. reusable-run validation exercises the same replay invariants as comparable construction.
12. probe discovery uses the storage API rather than coordinator-owned raw SQL.

### C. Comparable-first recovery

13. existing exact comparable replays equal and becomes authoritative even when a newer duplicate
    completed probe exists.
14. missing comparable is built once from selected run IDs.
15. corrupted/conflicting immutable comparable fails closed.
16. no partial family comparable is built after incomplete search.

### D. Concurrency and retry

17. default maximum active exact queries is four; CLI accepts only `1..4`.
18. independent queries overlap under a blocking mocked source.
19. pages of one query never overlap and preserve cursor order.
20. one-worker and four-worker mocked runs assemble equivalent manifest-ordered selected evidence.
21. no query is accidentally scheduled twice.
22. SQLite-affecting search persistence produces no lock errors/corruption under concurrent network
    execution.
23. existing transport exceptions retry at most three attempts with 1s/2s delay; semantic failures
    do not retry.

### E. Concurrent failure

24. terminal worker failure stops new scheduling.
25. active sibling may finish and its completed evidence is reusable on resume.
26. failed search stage preserves workdir and does not start comparables/downstream.
27. failure summary reports available worker/query/page/attempt context and safe resume command.

### F. Logs, heartbeat, timings

28. multi-worker emitter produces coherent append-only `run.log` and JSON event records.
29. resume never truncates logs and safely separates a simulated partial JSONL tail before new
    events.
30. heartbeat appears under fake-clock inactivity and carries thread-safe active-worker state.
31. timing report is manifest-ordered, distinguishes `collected` vs `reused`, and never invents
    previous-process network duration.
32. elapsed durations use an injectable monotonic clock.

### G. Downstream and artifact lifecycle

33. resumed run clears stale derived output and rebuilds snapshot/export/CSV/features.
34. fresh rebuild verification passes after recovery.
35. artifact selector excludes run-state/lock/logs/temp files and manifest builder/ZIP writer use the
    exact same payload set.
36. temporary ZIP is fully verified before final path publication.
37. simulated interruption leaves no partial file at the final export path.
38. existing fully valid final ZIP after simulated post-publication crash is recognized as terminal
    success; invalid existing final ZIP fails closed and is not overwritten.
39. failed verification/publication preserves workdir.
40. successful run deletes workdir only after verified final artifact + final hash.

### H. Regression / release

41. existing schema-v1 manifests remain accepted.
42. raw-before-interpretation and comparable provenance regression tests remain green.
43. package version is consistently `0.2.0`.
44. Ruff, strict mypy, full pytest suite, and coverage gate >=80% pass at exact release head.

The numbered list describes semantic coverage, not a required one-test-function-per-number layout.

---

## 40. Required real-world acceptance

Before declaring `0.2.0` complete, run the real target sweep:

```text
mystery-unboxing-collection-sweep-v1
15 families
36 exact queries
pages = 3
workers = 4
```

Acceptance evidence must show:

- live worker progress;
- no silent multi-minute execution window;
- actual search-stage wall duration;
- per-query/per-page timing evidence for the fresh invocation;
- rich-metadata duration;
- no SQLite corruption/locking regression;
- no obvious source-instability signal caused by four-worker collection;
- final verifier `PASS`;
- final ZIP hash.

Also perform a focused hard-kill/recovery acceptance with a controlled test manifest or the real
sweep when practical:

```text
start with workers=4
→ allow several queries to complete
→ hard-kill process
→ resume same workdir
→ completed selected queries reused
→ in-flight queries rerun from page 1
→ final verifier PASS
```

Do not weaken the analyst manifest merely to fit a shell timeout.

---

## 41. Definition of Done — Reaper 0.2.0

`0.2.0 — Resumable & Observable Experiments` is complete only when all of the following are true:

1. package version is consistently `0.2.0` and workflow is `analyst-experiment-v1.2`;
2. manifest schema v1 remains valid and unchanged;
3. one process exclusively owns a workdir at a time;
4. durable immutable run identity exists before source network I/O;
5. long runs emit append-only live stage/query/page/retry progress and heartbeat;
6. failures name the known stage/unit/worker/page/attempt/error and preserved workdir;
7. `resume <workdir>` validates identity before network and preserves original run ID/start time;
8. existing valid comparables are recovered first and remain authoritative for their selected runs;
9. valid reusable `COMPLETED` queries are replay-validated before reuse;
10. `RUNNING`, `PARTIAL`, and `FAILED` are never reused as completed query evidence;
11. interrupted queries restart from page 1;
12. exact-query search uses bounded concurrency with default four workers and CLI range `1..4`;
13. pagination inside each query remains sequential;
14. SQLite-affecting search persistence is safe under concurrent network work;
15. worker failure stops new scheduling but preserves valid completed siblings for resume;
16. missing comparables are built once; immutable conflicts fail closed;
17. downstream derivations are rebuilt cleanly rather than checkpointed generically;
18. rich metadata may be recollected and remains sequential;
19. final timing report accurately describes the successful invocation without fabricated
    interrupted-process timings;
20. artifact payload is explicit and does not accidentally package logs/run-state/locks/temp files;
21. final ZIP is built/verified at a temporary path and published create-only only after verification;
22. a crash after final publication but before cleanup is recoverable without overwriting the ZIP;
23. fresh snapshot/export/features rebuild verification passes;
24. failed run/resume preserves workdir;
25. successful run/resume deletes workdir only after verified artifact publication + final hash;
26. real four-worker Mystery/Unboxing/Collection acceptance succeeds operationally;
27. exact-head CI is green;
28. no scheduler, DAG, daemon, dashboard, distributed workers, generic checkpoint API, or other
    orchestration framework is introduced.

---

## 42. Explicit non-goals for 0.2.0

Do not add unless a concrete implementation blocker proves necessity:

```text
status command
pause command
cancel command
background daemon
job queue
scheduler / cron
distributed workers / cloud runner
worker fleet
generic DAG/task graph
generic checkpoint registry
rich-metadata batch resume
parallel rich-metadata collection
parallel downstream derivation
automatic worker tuning
proxy rotation / anti-bot evasion
cross-experiment query cache
cross-experiment evidence reuse
manifest worker configuration
manifest retry configuration
TTY dashboard / web dashboard
automatic opportunity scoring
taxonomy classifier
candidate dossier framework
```

---

## 43. Recommended implementation decomposition

All three PRs belong to the same `0.2.0` release. Separation is for reviewability, not optionality.

### PR A — Durable identity + observability

Scope:

```text
workflow v1.2 lifecycle constant / compatibility scaffolding
exclusive workdir lock
run-state.json
central event emitter
run.log / events.jsonl
stage/query/page/retry instrumentation
heartbeat
failure summary
timing model/report
explicit artifact payload selector foundation
```

No query concurrency or resume source reuse is required yet.

### PR B — Deterministic resume

Scope:

```text
resume CLI
workdir preflight
final-artifact terminal-success recovery
probe discovery read API
shared reusable-run validation
comparable-first authoritative recovery
original run identity
stale/partial/failed rerun
missing comparable build
downstream clean rebuild
resume logging
crash-safe temporary package publication
```

Internal query execution may remain `workers=1` until PR C if that materially simplifies review.

### PR C — Bounded exact-query concurrency

Scope:

```text
default 4 workers
--workers 1..4
global stable exact-query scheduling
sequential pages per query
isolated sessions
serialized SQLite-affecting persistence
thread-safe event emitter/heartbeat state
manifest-order result assembly
concurrent failure semantics
concurrency/equivalence tests
```

`0.2.0` MUST NOT ship after only PR A + PR B.

If the PRs are merged incrementally to `main`, do not advertise package version `0.2.0` until the
full release Definition of Done is present. Apply the authoritative `0.2.0` package-version bump in
the final integration/concurrency PR or a dedicated release commit after PR C.

---

## 44. Release focus after completion

This release exists to unblock real opportunity discovery.

Immediately after `0.2.0` is verified:

```text
run/resume Mystery / Unboxing / Collection sweep
→ verify artifact
→ inspect query-level coherence
→ fresh outliers
→ developer concentration
→ descriptions / instructions
→ production burden
→ reward strength
→ re-themeability
→ clone graveyards
→ 1–3 concrete ultra-cheap game theses
→ BUILD / WATCH / SKIP
```

Do not automatically start a new infrastructure milestone.

The next product question is:

> **Which concrete ultra-simple game opportunity does the recovered deep sweep support?**
