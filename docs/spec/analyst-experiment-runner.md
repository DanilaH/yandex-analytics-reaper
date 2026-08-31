# Analyst Experiment Runner v1.1

## Status

This specification defines the thin operator-facing runner added after real `START ANALYSIS`
usage exposed repeated manual-orchestration failures. It does not replace the low-level probe,
query-family, comparable-set, snapshot, export, or feature contracts.

The runner exists to remove decisions that should never belong to a local coding agent:

```text
versioned manifest
→ exact query execution
→ declared-family comparable sets
→ rich metadata batching
→ frozen snapshot/export/features
→ verification
→ immutable package
```

It is intentionally **not** a workflow framework, scheduler, discovery policy, taxonomy
classifier, or opportunity scorer.

## Input contract

A run starts from one strict JSON manifest:

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
    },
    {
      "id": "break-reveal",
      "queries": ["break", "сломай", "что внутри"]
    }
  ]
}
```

`experiment_id` and family IDs are human-readable lowercase slugs. The manifest is validated
before the first network request.

Family semantics are analyst-owned:

- the runner never infers, merges, renames, or reassigns families;
- an exact query may appear in only one family in one manifest;
- the first query is persisted as the query-family seed;
- remaining declared queries are persisted as `other`; the runner does not guess whether they
  are translations, synonyms, spelling variants, or something else;
- all query-level evidence remains visible even when the family union is later inspected.

`clean_anonymous` is the only session profile accepted by this v1 runner because
`yandex_search_union_v1` itself requires that evidence context. Collection depth and context
remain explicit provisional choices, not calibrated defaults.

Batch size, retry count, output paths, temporary paths, parser versions, and generated run IDs
are implementation details and do not belong in the experiment manifest.

## Command

```bash
yandex-reaper-experiment run path/to/experiment.json
```

The local agent should only execute the command. It must not create batch files, invent query
grouping, select output paths, or move experiment-owned files into a system temporary
directory.

## Run identity and paths

`experiment_id` identifies the human analytical experiment definition.

Every execution receives an automatically generated UTC `run_id`, for example:

```text
20260831T203412Z
```

A same-second collision receives a deterministic suffix rather than overwriting an existing run.

While executing, all experiment-owned state lives inside the repository:

```text
artifacts/work/<experiment_id>/<run_id>/
```

A successful immutable package is written create-only to:

```text
artifacts/exports/<experiment_id>/<run_id>.zip
```

A successful run deletes its work directory only after package verification and final ZIP
hashing. A failed run preserves the work directory and reports its path for diagnosis.

`artifacts/` is ignored by Git.

## Execution semantics

The coordinator reuses existing source/evidence boundaries rather than reimplementing their
semantics:

1. persist each exact declared query family;
2. collect one completed search run per exact query under one explicit `ProbeContext`;
3. build and persist one `yandex_search_union_v1` provisional comparable set per family;
4. preserve query-level membership and write descriptive coherence diagnostics;
5. deduplicate the comparable union across families;
6. collect `catalogue.get_games` rich metadata in internal batches of at most 100 IDs;
7. preserve raw responses before HTTP/schema/parser/normalization interpretation;
8. freeze an analyst snapshot from the exact comparable/rich evidence;
9. build analyst market export + CSV convenience tables;
10. build transparent market features;
11. rebuild the snapshot/export/features chain and require exact equality;
12. package all run evidence;
13. reopen the ZIP and verify its complete file set, byte sizes, and SHA-256 hashes;
14. hash the final ZIP;
15. delete the successful work directory.

No family coherence threshold is applied. Jaccard/intersection diagnostics are descriptive only.
A family union remains an analyst-declared provisional search-derived comparable set, not a
validated canonical market.

## Retry boundary

The runner has one deliberately narrow internal retry rule. It may repeat the exact same
query/context/depth or rich-metadata batch after:

```text
httpx.ConnectTimeout
httpx.ReadTimeout
httpx.ConnectError
```

There are at most three total attempts.

Search transport failures remain persisted by the existing probe-run store. A successful
comparable set binds only the selected completed run.

The runner does **not** retry semantic/source failures such as:

```text
partial probe result
HTTP source error after a response exists
breaking schema drift
parser failure
normalization failure
```

Those failures stop the experiment so they can be diagnosed without silently changing the
evidence cohort.

## Package contract

The ZIP contains, at minimum:

```text
input/manifest.json
raw/...
market.sqlite3
reports/analyst-snapshot.json
reports/market-export.json
reports/market-features.json
reports/family-coherence.json
reports/verification.json
csv/...
execution-summary.json
artifact-manifest.json
```

The input manifest is copied **verbatim**.

`execution-summary.json` records:

- workflow version;
- `experiment_id` and generated `run_id`;
- start/completion timestamps;
- source manifest SHA-256;
- package version;
- best-effort Git commit SHA;
- Python/platform runtime;
- family/query counts;
- comparable union size;
- requested/observed/missing rich-metadata coverage;
- snapshot/export/features content hashes;
- verifier status.

`artifact-manifest.json` contains the size and SHA-256 of every other packaged file. It cannot
contain the final ZIP hash because that would be self-referential.

After packaging, the runner reopens the ZIP and requires:

- no duplicate paths;
- no absolute or parent-traversal paths;
- exact agreement between ZIP entries and `artifact-manifest.json`;
- exact byte size and SHA-256 agreement for every payload file.

The final ZIP SHA-256 and `artifact-manifest.json` SHA-256 are printed by the CLI.

## Evidence boundary

The runner changes ergonomics, not analytical epistemology.

Keep all existing rules:

```text
raw before interpretation
immutable raw snapshots
derived values traceable to raw
missing != zero
totalGamesCount != competitor count
sponsored != organic
query-family union != validated taxonomy/canonical market
no opaque opportunity score
```

A source omission from `get_games` is recorded as missing rich metadata. It is not converted to
zero and does not cause the runner to invent replacement evidence.

## Definition of Done

v1.1 is complete when an operator can give the local agent one manifest and one command and,
without any further grouping/path/batching decisions, receive:

```text
immutable ZIP path
final ZIP SHA-256
artifact-manifest SHA-256
verifier = PASS
```

Another analyst must be able to unpack that ZIP and reconstruct what was requested, when it ran,
which Reaper/runtime produced it, which exact query runs formed each comparable set, and which
raw snapshots support the exported evidence.
