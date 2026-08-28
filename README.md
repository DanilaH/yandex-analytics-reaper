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

## Current status

**Phase 1 — Foundation is being finalized in PR #1.**

Implemented in the bootstrap branch:

- source capability contracts;
- immutable filesystem raw-snapshot store;
- platform-neutral domain primitives;
- evidence/candidate/taxonomy foundations;
- Yandex public-source HTTP client;
- source-specific parsers for `feed`, `search`, `get_games`, and `__playPageData__` response shapes;
- manual CLI probes that persist raw responses before parsing;
- fixture/unit tests;
- Ruff, strict mypy, pytest, and GitHub Actions quality gates;
- reviewed living specifications under `docs/spec/`.

Not implemented yet:

- source DTO → domain normalizers;
- normalized/database persistence and lineage persistence;
- scheduled collection;
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

All three are merge gates. A red CI run is not considered merge-ready.

## Manual Yandex probes

The current CLI is a **manual probe/debug interface**, not the production scheduled collector.

Feed:

```bash
yandex-reaper probe-feed --count 20 --output data/raw
```

Search:

```bash
yandex-reaper probe-search "merge" --output data/raw
```

Rich game metadata:

```bash
yandex-reaper probe-games 438560 354517 --output data/raw
```

Game page / `__playPageData__`:

```bash
yandex-reaper probe-page 438560 --output data/raw
```

Each probe persists the raw response before parsing.

## Read before changing the project

1. `AGENTS.md` — engineering/agent workflow;
2. `ARCHITECTURE.md` — package and ingestion boundaries;
3. `ROADMAP.md` — current phase and sequencing;
4. relevant living spec under `docs/spec/`;
5. relevant dated evidence under `docs/research/` when source behavior matters.

The live-probe evidence that motivated the Yandex adapter is preserved in:

`docs/research/YANDEX_PRELAUNCH_DATA_FEASIBILITY_2026-08-28.md`
