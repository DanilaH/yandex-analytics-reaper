# Yandex Analytics Reaper

Private market-intelligence tooling for discovering and evaluating Yandex Games opportunities.

The system is designed around two jobs:

```text
OPPORTUNITY DISCOVERY
market → candidate ideas

CANDIDATE EVALUATION
candidate → evidence → BUILD / WATCH / SKIP
```

It does **not** treat competitor proxies as an exact prediction of game success. The core analytical model is:

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

Repository foundation / Phase 1.

Implemented in this bootstrap:

- source capability contracts;
- immutable filesystem raw-snapshot store;
- evidence envelope and explicit unknown semantics;
- platform-neutral domain models;
- Yandex public-source HTTP client;
- parsers for `feed`, `get_games`, and `__playPageData__`;
- low-volume CLI probe that persists raw responses before parsing;
- taxonomy/candidate model foundations;
- tests, Ruff, mypy, and GitHub Actions;
- reviewed pre-development specification under `docs/predev/`.

Not implemented yet:

- database persistence;
- scheduled collection;
- final taxonomy classifier;
- historical backfill;
- backtest engine;
- UI/dashboard;
- ML scoring.

## Requirements

- Python 3.12+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
```

## Quality checks

```bash
ruff check .
mypy src
pytest
```

## Run a small Yandex probe

This command fetches one feed page, stores the raw response, and prints a parsed summary:

```bash
yandex-reaper probe-feed --count 20 --output data/raw
```

Search:

```bash
yandex-reaper probe-search "merge" --output data/raw
```

Fetch rich game metadata:

```bash
yandex-reaper probe-games 438560 354517 --output data/raw
```

The CLI intentionally performs only explicit user-triggered requests. Scheduling/orchestration belongs to a later phase.

## Read before changing architecture

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `ROADMAP.md`
4. `docs/predev/00_SYSTEM_PRINCIPLES_AND_DOR.md`
5. `docs/predev/07_PRODUCTION_DATA_MODEL_V2.md`

The live-probe evidence that motivated the current Yandex adapter is preserved in:

`docs/research/YANDEX_PRELAUNCH_DATA_FEASIBILITY_2026-08-28.md`
