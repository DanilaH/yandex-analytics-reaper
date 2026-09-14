# Durable Evidence Archive

`durable-evidence-archive-v1` defines how decision-relevant CI evidence survives beyond GitHub Actions artifact retention without changing Reaper's analytical evidence semantics.

It is a **durability and retrieval boundary**, not a new market-data model, not a scheduler, and not a replacement for the immutable experiment ZIP contracts already consumed by Thesis Intelligence.

## Problem

GitHub Actions artifacts are operational delivery objects with finite retention. Reaper 0.3 longitudinal analysis, however, intentionally compares a current frozen experiment with one or more explicitly bound prior experiment artifacts.

If the only copy of an older run is an expiring Actions artifact, later delta analysis can become impossible even though the analytical code and report hashes remain valid.

The durable archive therefore preserves the exact CI evidence bytes before the Actions retention window closes.

## Storage roles

```text
GitHub Actions artifact
  = temporary CI delivery/cache

Git repository request catalog
  = small, reviewable expected provenance + digest + release identity

GitHub Release assets
  = durable heavy evidence bytes + generated manifest/checksum

Existing Reaper experiment ZIP
  = analytical evidence unit consumed by current/prior-artifact logic
```

Large CI ZIPs must not be committed into normal Git history. `data/*` and `artifacts/*` remain runtime/working locations rather than a binary evidence warehouse.

## Byte-preserving rule

The primary Release asset is the **exact ZIP returned by GitHub's Actions artifact download endpoint**.

It must not be repacked, normalized, recompressed or otherwise rewritten before publication.

The archive builder computes SHA-256 over the downloaded bytes and requires exact agreement with the predeclared Actions artifact digest. For migrated runs, that expected digest comes from GitHub Actions artifact metadata.

This gives one byte identity across:

```text
Actions artifact metadata digest
= downloaded CI ZIP SHA-256
= durable Release asset SHA-256
= durable archive manifest artifact.sha256
```

If those values disagree, publication stops.

## Why the wrapper artifact is preserved

A research workflow can upload more than one useful output in one Actions artifact, for example:

```text
trend-mechanics-result.json
artifacts/exports/<experiment>/<run>.zip
artifacts/intelligence/<suite>/<hash>.zip
```

Preserving only one selected inner ZIP would discard other replay/debug evidence and weaken the direct provenance link to the original CI artifact.

V1 therefore archives the complete wrapper ZIP and records a deterministic inventory of every non-directory ZIP member:

```text
member path
uncompressed size_bytes
member SHA-256
```

A later consumer can verify the wrapper and then extract one exact bound inner experiment ZIP for the existing `yandex-reaper-thesis --prior <zip>` interface. No longitudinal analytical code needs to understand GitHub Releases.

## Request contract

Every durable archive begins with a small versioned request committed under:

```text
research/archive/requests/*.json
```

The request is the Git-resident catalog/index entry. It contains only expected immutable identity and publication addressing; it does not contain the heavy artifact bytes.

Schema:

```text
spec_version = durable-evidence-archive-request-v1
archive_id
source:
  workflow_run_id
  workflow_artifact_id
  workflow_artifact_name
  artifact_created_at
  artifact_expires_at
  source_commit_sha
  source_branch
expected:
  sha256
  size_bytes
release:
  tag
  asset_name
  manifest_asset_name
  checksum_asset_name
```

Rules:

- `archive_id` is stable and unique across the committed request catalog;
- release tag is unique across the committed request catalog;
- one Actions `workflow_artifact_id` cannot be assigned to two archive identities;
- archive IDs, release tags and asset names use a shell-safe `[A-Za-z0-9._-]` vocabulary;
- the three Release asset names are distinct;
- `artifact_expires_at` must be later than `artifact_created_at`;
- the expected SHA-256 and size bind one exact Actions artifact;
- source commit SHA is the commit that produced the CI artifact, not the later archival implementation commit;
- Release tag and asset names are fixed before publication;
- changing the evidence bytes requires a new archive identity, never a replacement under the old identity.

The workflow runs `yandex-reaper-archive validate-catalog` across the complete committed request set before making any Release side effects. Catalog identity collisions therefore fail as a preflight error rather than after partial publication.

## Generated manifest

After downloading and verifying the Actions artifact, `yandex-reaper-archive build` emits a create-only `durable-evidence-archive-v1` manifest.

It contains:

```text
archive_id
source provenance
release binding
artifact SHA-256 + size
sorted member inventory
content_hash
```

`content_hash` is SHA-256 over canonical JSON for all manifest fields except `content_hash` itself. It is a deterministic corruption/identity check, not a signature or proof of authorship.

The generated manifest is uploaded next to the wrapper ZIP as a Release asset. A sha256sum-compatible checksum file is uploaded as an additional human/tool-friendly check.

## Release publication

The GitHub Actions publisher uses the repository-scoped `GITHUB_TOKEN` with only the permissions required to read Actions artifacts and write Release contents.

Archive workflow runs are serialized by one repository-level concurrency group. A later trigger waits rather than canceling a publication already in progress.

Before downloading bytes, the workflow resolves the numeric Actions artifact and requires GitHub metadata to agree with the committed request for:

```text
artifact id
workflow run id
artifact name
created_at
expires_at
source commit SHA
source branch
size_in_bytes
SHA-256 digest
expired = false
```

Publication sequence:

```text
validate complete request catalog
→ resolve exact Actions artifact metadata
→ verify committed provenance + digest + size
→ download exact Actions artifact by numeric artifact ID
→ verify downloaded SHA-256 + size offline
→ inventory members + build manifest
→ create draft Release at the source commit
→ upload wrapper ZIP + manifest + checksum without clobber
→ download the Release assets again
→ verify request + manifest + wrapper + checksum
→ publish Release
```

Creating a draft before attaching assets is deliberate. If the repository enables GitHub's immutable-releases setting, publishing then also gives platform-level protection against changing the release tag or assets. The Reaper contract does **not** silently assume that repository setting is enabled: create-only workflow behavior plus hash verification remains mandatory either way.

A published release is never repaired by overwriting an existing asset. A conflicting existing tag/asset is an integrity failure. A partially created **draft** may only be completed with missing assets; already-present assets are never replaced and the complete draft must pass the same download-and-verify gate before publication.

## Reconciliation / rerun semantics

Archival workflows are expected to be rerunnable.

For each request:

1. if no Release exists, perform first publication;
2. if a Release exists, require its target commit to equal the committed source SHA;
3. if all three assets exist, download wrapper, manifest and checksum;
4. verify wrapper SHA-256/size/member inventory/content hash and request binding;
5. verify the checksum file against the downloaded wrapper;
6. if all checks pass, report the archive as already satisfied;
7. if a published Release is incomplete or any identity differs, fail closed;
8. if an incomplete draft exists, add only missing assets and then run the full verification gate;
9. never pass `--clobber` or otherwise replace evidence under the same archive identity.

This makes a successful rerun idempotent while keeping evidence create-only.

## Retrieval for longitudinal analysis

A future longitudinal run should resolve a prior artifact from the committed request catalog and corresponding Release, not from an old chat message or expired Actions URL.

High-level retrieval:

```text
archive request
→ Release wrapper ZIP + manifest
→ yandex-reaper-archive verify --request <request>
→ choose exact manifest member path
→ yandex-reaper-archive extract
→ resulting verified experiment ZIP
→ existing yandex-reaper-thesis --prior <zip>
```

`extract` verifies the complete wrapper first and then requires the extracted member's size and SHA-256 to equal its manifest binding before replacing the requested output path.

The analytical boundary remains:

```text
verified local experiment ZIP
→ existing load_experiment_artifact_binding(... role="prior")
→ existing experiment artifact verification
→ existing longitudinal feature logic
```

The durable archive cannot make an invalid experiment ZIP valid.

## Security and path handling

V1 treats ZIP contents as untrusted bytes until validated.

The inventory/extraction implementation:

- rejects absolute member paths;
- rejects `..` traversal;
- rejects ambiguous backslash paths;
- rejects duplicate file member names;
- extracts only an exact member already bound by the manifest;
- writes through a temporary file and replaces the destination only after member hash/size verification.

No unit test may call GitHub or any other network service. GitHub API/release transport remains workflow infrastructure around the offline archive core.

## Failure semantics

Archive publication/retrieval fails closed when:

- committed catalog identities collide;
- GitHub artifact provenance disagrees with the request;
- expected wrapper digest or size differs;
- the Actions artifact has already expired before a durable copy exists;
- the downloaded object is not a readable ZIP;
- ZIP member paths are unsafe or duplicated;
- an existing Release targets a different source commit;
- an existing published Release is incomplete;
- an existing Release uses the same tag with different bytes/provenance;
- a manifest content hash or member inventory does not replay;
- the requested inner member is absent;
- an extracted member hash or size differs.

Missing durable history must remain **missing history**. The system must never fabricate a prior observation or silently fall back to another run.

## Retention policy

Once durable publication is verified, Actions retention is only an operational convenience. Workflows may keep a finite Actions retention window for debugging; changing that window does not change the durable evidence identity.

The durable archive must be created while the Actions source artifact is still retrievable.

## V1 non-goals

Do not expand this feature into:

```text
S3/object-storage abstraction
artifact database
scheduler/daemon
automatic market recollection
release lifecycle manager
cross-repository data lake
transparent remote --prior URL support
a new experiment ZIP format
new analytical scoring or delta semantics
```

If Release storage later becomes inadequate, a new transport can implement the same digest-bound request/manifest semantics without rewriting the analytical evidence model.
