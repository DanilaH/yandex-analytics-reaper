# Yandex Analytics Reaper

Private market-intelligence tooling for discovering and evaluating Yandex Games opportunities.

The system has two jobs:

```text
OPPORTUNITY DISCOVERY
market → candidate ideas

CANDIDATE EVALUATION
candidate → evidence → BUILD / WATCH / SKIP
```

It does **not** treat competitor proxies as an exact prediction of game success. The analytical model is:

```text
Market Prior
+ Production Assessment
+ Evidence Quality
→ Decision
→ Our Release
→ Actual Metrics
→ Calibration
```

## Current scope

**Phase 1 — Foundation** is complete. **Phase 2 — Yandex market state** is in progress.

Implemented:

- source capability contracts;
- immutable filesystem raw-snapshot store with deterministic metadata/body replay and content-integrity checks;
- platform-neutral domain primitives;
- explicit source DTO → domain normalizer boundary;
- SQLite operational persistence for normalized listing/developer identities and developer-assignment history;
- normalized numeric metric persistence with observation/evidence envelopes and versioned normalizer metadata;
- field-level metric lineage from exact parser source path back to raw snapshot identity;
- versioned schema-drift monitoring for Yandex JSON surfaces with field/type/missingness contracts, scoped temporal comparisons, parser-failure records, and raw-content identity checks;
- logical paginated feed/search probe runs with deterministic context identity, ordered page/cursor linkage, terminal status, and raw error provenance;
- explicit `clean_anonymous` and `persistent_anonymous` HTTP session mechanics for contextual feed/search probes, with stable non-secret persistent-profile instance IDs plus safe cookie-state fingerprint/profile-age provenance;
- frozen `feed-depth-v1` protocol plus replay/analyzer tooling for explicit stored trials; the empirical calibration result is still pending;
- frozen `session-profile-stability-v1` matched-block protocol plus replay/analyzer tooling for explicit clean/persistent feed blocks; empirical per-depth classifications are still pending;
- immutable versioned search query-family declarations with exact ordered query membership and SQLite persistence;
- shared versioned SQLite migrations for the operational store;
- evidence/candidate/taxonomy foundations;
- Yandex public-source HTTP client;
- source-specific parsers for `feed`, `search`, `get_games`, and `__playPageData__` response shapes;
- Yandex game metadata normalizers;
- manual CLI probes that persist raw responses before parsing and stop interpretation on breaking JSON contract drift;
- fixture/unit tests;
- Ruff, strict mypy, pytest, and GitHub Actions quality gates;
- reviewed living specifications under `docs/spec/`.

Not implemented yet:

- empirical feed-depth recommendation from the required real `feed-depth-v1` trial sample;
- empirical session-profile classifications from the required real matched-block sample;
- query-family execution/result union and comparable-set construction;
- authenticated test-session credential provider;
- production scheduled collection and empirically selected collection cadence;
- validated taxonomy classifier;
- historical backfill/backtesting;
- external trend connectors;
- UI/dashboard;
- calibrated ML/ranking model.

See `ROADMAP.md` for the authoritative sequence and phase Definition of Done.

## Repository structure

```text
src/yandex_analytics_reaper/   application/source/domain code
tests/                         unit/fixture-driven tests
data/                          local runtime data; collected/session data is gitignored
docs/spec/                     living analytical/domain specifications
docs/research/                 dated factual probes/research evidence
docs/history/                  historical review/decision records
```

## Requirements

- Python 3.12+

## Setup

POSIX shell:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Quality checks

```bash
ruff check .
mypy src
pytest
```

All three remain required quality checks. GitHub-hosted CI is currently treated as infrastructure-only when it fails before allocating a runner; development/review continues with local/focused checks where available.

## Manual Yandex probes

The current CLI is a **manual probe/debug interface**, not the production scheduled collector.

Feed, one page and a fresh anonymous session by default:

```bash
yandex-reaper probe-feed --count 20 --output data/raw
```

Explicit multi-page feed run:

```bash
yandex-reaper probe-feed --count 20 --pages 3 --output data/raw
```

Persistent anonymous feed profile reused across runs:

```bash
yandex-reaper probe-feed --pages 3 --session-profile persistent_anonymous --output data/raw
```

Search, one page and a fresh anonymous session by default:

```bash
yandex-reaper probe-search "merge" --output data/raw
```

Explicit persistent multi-page search run:

```bash
yandex-reaper probe-search "merge" --pages 3 --session-profile persistent_anonymous --output data/raw
```

Rich game metadata:

```bash
yandex-reaper probe-games 438560 354517 --output data/raw
```

Game page / `__playPageData__`:

```bash
yandex-reaper probe-page 438560 --output data/raw
```

For feed/search, `clean_anonymous` creates a fresh cookie jar for every logical run. `persistent_anonymous` stores and reuses one local anonymous cookie jar under the runtime `sessions/` directory. Raw cookie values stay only in that local session-state file; raw snapshots and SQLite probe contexts receive the session profile, a stable non-secret local profile-instance ID, a SHA-256 cookie-state fingerprint, and profile age. The instance ID stays stable across ordinary cookie churn and changes after an explicit local profile reset; it is not a Yandex user/account identifier. Do not commit or share the runtime session directory.

`authenticated_test` is intentionally fail-closed until an explicit credential provider exists; selecting it does not silently run an anonymous probe.

Feed/search probes persist each raw response before interpretation and group pages into one logical run. Each later page must consume the exact continuation tokens emitted by the preceding page. A run is persisted as `completed`, `partial`, or `failed`; when a received raw response caused a terminal error, the run retains that raw snapshot ID for inspection.

JSON feed/search/get-games probes also record structural schema analyses; breaking contract drift stops interpretation after the raw response is safely stored. The HTML game-page path currently records parser failures but does not run the generic JSON structural profiler over raw HTML.

## Feed-depth calibration tooling

`feed-depth-v1` is frozen in `docs/spec/feed-depth-experiment.md`. It compares maximum depths `1 / 3 / 5 / 10` without collecting four independent runs per trial: each real trial is collected once with a maximum of 10 pages, then the analyzer derives all candidate prefixes from the same immutable raw run.

Collect eligible baseline trials with the frozen context:

```bash
yandex-reaper probe-feed \
  --count 20 \
  --pages 10 \
  --session-profile clean_anonymous \
  --lang ru \
  --device desktop \
  --platform desktop_other \
  --output data/raw
```

A legitimate source exhaustion before page 10 is still eligible. Partial/failed runs, wrong context/page size, broken raw data, and inconsistent replay linkage are rejected by the analyzer rather than silently coerced.

Do not make a depth decision until there are at least 8 eligible trials spanning at least 4 hours and 3 distinct UTC hour buckets. Then analyze the **explicit** run IDs:

```bash
yandex-reaper analyze-feed-depth \
  probe:<run-id-1> \
  probe:<run-id-2> \
  probe:<run-id-3> \
  --output data/raw
```

The command replays raw bodies, verifies content hashes and stored page linkage, excludes sponsored cards from depth selection, reports rejected trials, and applies the predeclared thresholds. Until the minimum sample is satisfied it returns `recommended_depth = null`; do not treat synthetic fixture tests as the empirical calibration result.

## Session-profile stability tooling

`session-profile-stability-v1` is frozen in `docs/spec/session-profile-stability-experiment.md`. It compares `clean_anonymous` with one controlled `persistent_anonymous` profile without consuming the pending feed-depth recommendation: every run is requested up to 10 pages and the analyzer reports profile stability independently for depths `1 / 3 / 5 / 10`.

One matched block contains four runs whose starts fall within 10 minutes. Alternate the two frozen orders across blocks:

```text
C-P-P-C
P-C-C-P
```

where `C` is `clean_anonymous` and `P` is `persistent_anonymous`. Use the same local persistent profile for every `P` run in the entire experiment; do not reset the local persistent profile between blocks.

Each run uses the same frozen feed shape:

```bash
yandex-reaper probe-feed \
  --count 20 \
  --pages 10 \
  --session-profile clean_anonymous \
  --lang ru \
  --device desktop \
  --platform desktop_other \
  --output data/raw
```

For a `P` position, use the same command with `--session-profile persistent_anonymous`. Record every returned run ID. The analyzer derives chronological order from persisted timestamps, so the caller does not need to fake or encode chronology in the ID order.

Do not classify any depth until there are at least 6 eligible blocks spanning at least 4 hours and 3 distinct UTC hour buckets, including at least 2 `C-P-P-C` and 2 `P-C-C-P` blocks. Analyze explicit block membership with repeated `--block` arguments:

```bash
yandex-reaper analyze-session-profile-stability \
  --block probe:<c1> probe:<p1> probe:<p2> probe:<c2> \
  --block probe:<p3> probe:<c3> probe:<c4> probe:<p4> \
  --output data/raw
```

The report replays immutable raw bodies, verifies stored page linkage and frozen request context, rejects corrupt/ineligible blocks, requires one persistent `session_instance_id` across all eligible blocks, and classifies every depth as `stable`, `material_difference`, or `inconclusive` only after the minimum sample is sufficient. Synthetic fixtures are never empirical evidence.

## Search query-family model

`docs/spec/search-query-family.md` owns the versioned declaration semantics. A family version freezes one source/language intent into an ordered tuple of exact outgoing query strings with one canonical seed and controlled variant kinds.

SQLite persistence is immutable by `(family_id, version)`: repeating the exact same declaration is idempotent, while changing label/source/language/member text/kind/order under an existing version is rejected. Create a new version instead.

This layer deliberately does not generate synonyms, execute the family, union result sets, or build comparable sets. Existing manual search probes continue to persist the exact `query_text` actually sent; later execution/comparable-set work must bind those runs to an exact declared family/version rather than infer membership fuzzily.

## Read before changing the project

1. `AGENTS.md` — engineering/agent workflow;
2. `ARCHITECTURE.md` — package and ingestion boundaries;
3. `ROADMAP.md` — current phase and sequencing;
4. relevant living spec under `docs/spec/`;
5. relevant dated evidence under `docs/research/` when source behavior matters.

The live-probe evidence that motivated the Yandex adapter is preserved in:

`docs/research/YANDEX_PRELAUNCH_DATA_FEASIBILITY_2026-08-28.md`
