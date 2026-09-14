# Durable evidence archive catalog

This directory is the Git-resident catalog for heavy CI evidence that must survive GitHub Actions artifact retention.

The large evidence ZIPs themselves do **not** belong in normal Git history. Each `requests/*.json` file binds one exact historical Actions artifact by numeric workflow/artifact identity, SHA-256, size, source commit and durable GitHub Release address.

Normative semantics live in [`docs/spec/durable-evidence-archive.md`](../../docs/spec/durable-evidence-archive.md).

## Current migration set

The initial migration preserves the four September 13 trend-mechanics sweeps used by the current Yandex Games decision evidence:

```text
trend-mechanics-round2-2026-09-13
trend-mechanics-round3-2026-09-13
trend-mechanics-round4-2026-09-13
trend-mechanics-round5-2026-09-13
```

**Migration status:** COMPLETE 2026-09-14.

All four Actions wrappers were published as durable GitHub Releases before their 2026-10-13 retention expiry. The live workflow redownloaded each wrapper, manifest and checksum and verified the committed request binding plus `sha256sum` before publication.

Acceptance evidence:
[`docs/history/durable-evidence-archive-live-migration-2026-09-14.md`](../../docs/history/durable-evidence-archive-live-migration-2026-09-14.md).

GitHub currently reports `immutable = false` for these Releases. The archive contract therefore continues to rely on create-only/no-clobber workflow behavior and cryptographic request/manifest verification rather than assuming repository-level immutable releases are enabled.

## Adding a future archive

1. Obtain the successful Actions artifact metadata from GitHub.
2. Add one new create-only `durable-evidence-archive-request-v1` JSON file under `requests/`.
3. Bind the exact artifact digest/size and producing source commit.
4. Use a new stable `archive_id` and Release tag; never reuse an old identity for different bytes.
5. Merge through normal CI/review. The durable archive workflow reconciles committed requests into Release assets.
6. Verify the Release before relying on it as historical evidence.

The request files are intentionally small and human-reviewable. Generated member inventories live beside the heavy Release asset in the generated manifest.
