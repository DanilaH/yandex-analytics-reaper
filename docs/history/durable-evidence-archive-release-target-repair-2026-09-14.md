# Durable Evidence Archive Release-Target Repair — 2026-09-14

## Trigger

The Keycap P1 point-observation baseline passed the durable-archive catalog validation, exact GitHub Actions provenance checks, wrapper SHA-256/size verification, ZIP inventory, and manifest build, but Release creation failed twice with:

```text
HTTP 403: Resource not accessible by integration
```

The failing source commit was `10251bacf237ee6656a44b3d53251135ae10c166`. That historical commit differs from the current default branch under `.github/workflows/` because it contained temporary validation workflow state.

A second bounded experiment confirmed the same permission boundary from the opposite direction: a `GITHUB_TOKEN` job with `contents: write` could create the local repair commit but GitHub rejected the push because it attempted to update `.github/workflows/` without workflow-write permission.

## Root cause

The archive implementation incorrectly treated the GitHub Release target commit as evidence provenance and therefore always created a Release with:

```text
--target <source_commit_sha>
```

For a historical target that differs in workflow files, GitHub can require workflow-write authorization that the repository-scoped Actions `GITHUB_TOKEN` cannot provide.

The Release target was redundant as an integrity control. The archive already binds the actual evidence source through the committed request and verifies it against the numeric Actions artifact metadata before download:

```text
workflow run id
artifact id/name
created_at / expires_at
workflow_run.head_sha
workflow_run.head_branch
size_in_bytes
SHA-256 digest
expired = false
```

The downloaded wrapper is then checked again by exact SHA-256/size, inventoried into the manifest, uploaded create-only, redownloaded, and reverified before publication.

## Repair

No request schema, manifest schema, artifact bytes, content hash, or analytical semantics change.

The workflow now:

- creates new Releases at the current archive-workflow commit (`GITHUB_SHA`), which is only a safe transport pointer;
- retains the original `source.source_commit_sha` as the evidence provenance and still requires exact equality with `workflow_run.head_sha`;
- treats an existing Release target as informational only;
- continues to verify the Release tag, exact asset names, request binding, wrapper SHA/size, manifest/member identity, and checksum;
- remains create-only and never uses `--clobber`.

Existing Releases that already target their historical source commits require no migration and remain valid.

## Why this is narrower than adding another request field

An earlier repair direction considered adding a request-only `release_target_commit_sha`. Independent review rejected that as unnecessary state: if a Release target is not evidence provenance, binding it into the request would create another durable identity field with no analytical value.

Keeping transport placement outside the evidence contract preserves the original `durable-evidence-archive-request-v1` and `durable-evidence-archive-v1` formats unchanged.

## Acceptance

This repair is live-complete only when:

1. repository CI passes on the final PR head;
2. independent diff review confirms no temporary workflow or evidence-schema changes remain;
3. the PR is merged to `main`;
4. the post-merge durable archive workflow successfully creates the missing Keycap baseline Release;
5. all three Release assets are redownloaded and verified by the existing workflow before publication;
6. a subsequent reconciliation run recognizes the published archive as already satisfied without mutating it.
