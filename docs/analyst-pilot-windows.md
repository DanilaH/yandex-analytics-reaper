# Analyst Pilot — Windows Runbook

This runbook is for the first real M1.4 pilot on the operator machine. It assumes the repository is already cloned locally and that real network access to Yandex is available.

The goal is deliberately narrow:

```text
2 distinct market questions/query families
→ real search evidence
→ 2 reproducible comparable sets
→ rich metadata (+ optional feed)
→ frozen analyst snapshot
→ market export
→ market features
→ offline pilot verification
→ human review of limitations/usability
```

Do not treat synthetic fixtures as a substitute for this run.

## 0. Update and verify the local environment

PowerShell:

```powershell
git checkout main
git pull --ff-only

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

ruff check .
mypy src
pytest
```

If the virtual environment already exists, activate it and reinstall the editable project only when needed.

Keep the entire pilot in one evidence workspace:

```powershell
$RAW = "data/raw"
$ANALYSIS = "data/analysis/pilot-v0"
New-Item -ItemType Directory -Force $ANALYSIS | Out-Null
```

`$RAW` and the adjacent `data/market.sqlite3` must remain together. Do not copy only the final JSON files and discard the raw store.

## 1. Choose two actual market questions

Use two distinct `query_family_id` values. The first technical pilot may use simple concrete niches such as `merge-games` and `obby-games`, but the strings are not mandated by the tooling.

Each family should contain one seed plus only variants that you are willing to treat as the same search intent for this pilot.

Example family A:

```json
{
  "family_id": "merge-games",
  "version": 1,
  "label": "merge games",
  "source_id": "yandex_public",
  "language": "ru",
  "created_at": "<UTC timestamp before persistence>",
  "members": [
    {"query_text": "merge", "kind": "seed"},
    {"query_text": "слияние", "kind": "synonym"}
  ]
}
```

Example family B:

```json
{
  "family_id": "obby-games",
  "version": 1,
  "label": "obby games",
  "source_id": "yandex_public",
  "language": "ru",
  "created_at": "<UTC timestamp before persistence>",
  "members": [
    {"query_text": "obby", "kind": "seed"},
    {"query_text": "обби", "kind": "synonym"}
  ]
}
```

Save them under `$ANALYSIS`, then persist both:

```powershell
yandex-reaper-analyst persist-query-family "$ANALYSIS/merge-family.json" --output $RAW
yandex-reaper-analyst persist-query-family "$ANALYSIS/obby-family.json" --output $RAW
```

## 2. Collect real search evidence

Use one explicit context and one explicit provisional page limit for every query in both families. For the first pilot, keep the current documented baseline unless there is a concrete reason not to:

```text
language = ru
device = desktop
platform = desktop_other
session_profile = clean_anonymous
pages = 3
```

Example:

```powershell
yandex-reaper probe-search "merge" --pages 3 --session-profile clean_anonymous --lang ru --device desktop --platform desktop_other --output $RAW
yandex-reaper probe-search "слияние" --pages 3 --session-profile clean_anonymous --lang ru --device desktop --platform desktop_other --output $RAW

yandex-reaper probe-search "obby" --pages 3 --session-profile clean_anonymous --lang ru --device desktop --platform desktop_other --output $RAW
yandex-reaper probe-search "обби" --pages 3 --session-profile clean_anonymous --lang ru --device desktop --platform desktop_other --output $RAW
```

Record every returned `run_id`. Do not use a PARTIAL/FAILED run in the pilot comparable set.

## 3. Build two comparable sets

After the search runs finish, create one declaration per family. Set `created_at` to a current UTC timestamp **after** the referenced search evidence was collected.

Example shape:

```json
{
  "construction_method": "yandex_search_union_v1",
  "set_id": "merge-games-search",
  "version": 1,
  "query_family_id": "merge-games",
  "query_family_version": 1,
  "created_at": "<UTC timestamp after search collection>",
  "run_ids": [
    "probe:<merge-run-id>",
    "probe:<slianie-run-id>"
  ]
}
```

Build both:

```powershell
yandex-reaper-analyst build-search-comparable-set "$ANALYSIS/merge-comparable.json" --output $RAW
yandex-reaper-analyst build-search-comparable-set "$ANALYSIS/obby-comparable.json" --output $RAW
```

Keep the printed persisted comparable-set outputs. They contain the member listing IDs needed for enrichment.

## 4. Collect rich metadata

Collect `get_games` metadata for the comparable members. `probe-games` accepts at most 100 IDs in one request, so split larger peer sets into batches.

```powershell
yandex-reaper probe-games <app-id-1> <app-id-2> <app-id-3> --output $RAW
```

Record every printed `raw_snapshot=<id>` value. The snapshot may have partial rich-metadata coverage, but the pilot should contain enough observed quantitative metadata to make each comparable set analytically usable.

Use `probe-page` only where page-level update/ad/leaderboard/purchase metadata is useful:

```powershell
yandex-reaper probe-page <app-id> --output $RAW
```

## 5. Optional feed evidence

Feed is not mandatory for `START ANALYSIS`. If you want feed exposure in the first pilot, collect it under the same effective context:

```powershell
yandex-reaper probe-feed --pages 3 --session-profile clean_anonymous --lang ru --device desktop --platform desktop_other --output $RAW
```

Record the returned feed `run_id`.

If feed is skipped, the feature/pilot reports preserve that as unavailable evidence rather than a zero exposure claim.

## 6. Freeze the analyst snapshot

Create one `AnalystSnapshotDeclaration` containing both comparable-set versions, optional feed run IDs, and all rich-metadata raw snapshot IDs used by the pilot.

Use a `created_at` later than every bound piece of evidence.

```powershell
yandex-reaper-analyst build-snapshot "$ANALYSIS/snapshot-declaration.json" --report "$ANALYSIS/snapshot.json" --output $RAW
```

The command fails closed on incompatible contexts/depths, incomplete probe evidence, raw replay mismatch, unrelated rich metadata, or invalid time boundaries.

## 7. Export the frozen market evidence

```powershell
yandex-reaper-analyst export-snapshot "$ANALYSIS/snapshot.json" --report "$ANALYSIS/market-export.json" --csv-dir "$ANALYSIS/csv" --output $RAW
```

Do not edit the generated JSON/CSV files in place.

## 8. Build transparent market features

```powershell
yandex-reaper-analyst build-market-features "$ANALYSIS/snapshot.json" "$ANALYSIS/market-export.json" --report "$ANALYSIS/market-features.json"
```

This is an offline file-to-file derivation. No network or SQLite access is used.

## 9. Run the pilot verifier

```powershell
yandex-reaper-analyst verify-pilot "$ANALYSIS/snapshot.json" "$ANALYSIS/market-export.json" "$ANALYSIS/market-features.json" --report "$ANALYSIS/pilot-verification.json" --output $RAW
```

A successful verifier run proves that:

```text
there are at least two distinct query families
snapshot/export/features form one exact hash chain
features reproduce exactly from the frozen snapshot/export
available numeric aggregates reproduce from listing-level values
aggregate contributions retain observation/raw/source-field provenance
all referenced raw bodies still exist and pass content-hash replay
search/feed/rich raw request-key ownership is consistent
normalized listing evidence does not escape the frozen rich-metadata set
```

It does not by itself close `START ANALYSIS`.

## 10. What to send back for final review

Preserve the whole local `data/` workspace. For the final review, provide at least:

```text
data/analysis/pilot-v0/snapshot.json
data/analysis/pilot-v0/market-export.json
data/analysis/pilot-v0/market-features.json
data/analysis/pilot-v0/pilot-verification.json
data/analysis/pilot-v0/csv/
data/raw/
data/market.sqlite3
```

If transferring the full raw workspace is inconvenient, do not delete it. The final gate cannot be declared complete from the four summary JSON files alone if the referenced raw evidence cannot be replayed.

## Final gate

After the real run, the final review still needs to answer:

```text
Can two real niches be compared without ad-hoc SQL or hidden assumptions?
Are representative aggregates traceable to the exact raw evidence?
Are missingness and provisional assumptions visible enough to avoid false confidence?
Did the real source expose any practical blocker that the synthetic tests could not reveal?
```

Only after those questions pass should M1.4 be checked off and `START ANALYSIS` be declared ready.