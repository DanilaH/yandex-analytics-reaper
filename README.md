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
- immutable filesystem raw-snapshot store with deterministic snapshot lookup;
- platform-neutral domain primitives;
- explicit source DTO → domain normalizer boundary;
- SQLite operational persistence for normalized listing/developer identities and developer-assignment history;
- normalized numeric metric persistence with observation/evidence envelopes and versioned normalizer metadata;
- field-level metric lineage from exact parser source path back to raw snapshot identity;
- versioned schema-drift monitoring for Yandex JSON surfaces with field/type/missingness contracts, scoped temporal comparisons, parser-failure records, and raw-content identity checks;
- logical paginated feed/search probe runs with deterministic context identity, ordered page/cursor linkage, terminal status, and raw error provenance;
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

- technical session-profile isolation/reuse semantics for clean vs persistent collection;
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
data/                          local runtime data; collected data is gitignored
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

Feed, one page by default:

```bash
yandex-reaper probe-feed --count 20 --output data/raw
```

Explicit multi-page feed run:

```bash
yandex-reaper probe-feed --count 20 --pages 3 --output data/raw
```

Search, one page by default:

```bash
yandex-reaper probe-search "merge" --output data/raw
```

Explicit multi-page search run:

```bash
yandex-reaper probe-search "merge" --pages 3 --output data/raw
```

Rich game metadata:

```bash
yandex-reaper probe-games 438560 354517 --output data/raw
```

Game page / `__playPageData__`:

```bash
yandex-reaper probe-page 438560 --output data/raw
```

Feed/search probes persist each raw response before interpretation and group pages into one logical run. Each later page must consume the exact continuation tokens emitted by the preceding page. A run is persisted as `completed`, `partial`, or `failed`; when a received raw response caused a terminal error, the run retains that raw snapshot ID for inspection.

JSON feed/search/get-games probes also record structural schema analyses; breaking contract drift stops interpretation after the raw response is safely stored. The HTML game-page path currently records parser failures but does not run the generic JSON structural profiler over raw HTML.

## Read before changing the project

1. `AGENTS.md` — engineering/agent workflow;
2. `ARCHITECTURE.md` — package and ingestion boundaries;
3. `ROADMAP.md` — current phase and sequencing;
4. relevant living spec under `docs/spec/`;
5. relevant dated evidence under `docs/research/` when source behavior matters.

The live-probe evidence that motivated the Yandex adapter is preserved in:

`docs/research/YANDEX_PRELAUNCH_DATA_FEASIBILITY_2026-08-28.md`
