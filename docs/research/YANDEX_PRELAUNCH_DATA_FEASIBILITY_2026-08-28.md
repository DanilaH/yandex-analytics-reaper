# Yandex Pre-launch Data Feasibility — 2026-08-28

This dated research note preserves the factual findings that justified the current Yandex adapter. It is evidence/history, not the living architecture specification.

## Probe provenance

Controlled local live probes were executed on **2026-08-28** using the second probe implementation (`v2`).

Core observation context:

```text
language: ru
device type: desktop
platform: desktop_other
auth: not required in the tested requests
feed depth: 3 pages
rich game-page samples: 10
search terms: merge, obby
```

Representative feed request parameters included:

```text
games_count=20
with_promos=false
lang=ru
device-type=desktop
platform=desktop_other
```

The endpoint returned 24 cards per observed feed page despite the requested count of 20. The three-page observation therefore produced 72 unique cards.

The raw run archive was preserved during the research session but is intentionally not committed to this repository as collected runtime market data. If the experiment is repeated, the new run must store its own raw snapshots and context rather than treating the counts below as timeless platform facts.

## Live endpoints confirmed

The controlled probes successfully received HTTP 200 responses from:

```text
GET  https://yandex.ru/games/api/catalogue/v2/feed/
GET  https://yandex.ru/games/api/catalogue/v2/search
POST https://yandex.ru/games/api/catalogue/v2/get_games
GET  https://yandex.ru/games/app/<appID>
```

## Feed/search behavior confirmed

The v2 probe confirmed:

```text
feed pagination
search pagination
search totalGamesCount
organic/sponsored separation
```

In this specific three-page feed observation there were **72 unique cards: 63 organic and 9 clearly sponsored**.

Search examples in this observation returned:

```text
merge → totalGamesCount 411
obby  → totalGamesCount 393
```

These are query-result counts under the tested request context, not canonical counts of games implementing those mechanics.

## Rich game metadata confirmed

Current responses exposed fields including:

```text
appID
title
developer id/name
categoryIDs/categoriesNames
tagIDs
rating
ratingCount
score[1..5]
gqRating
firstPublished
publishedTime
appVersion
minLoadTime
languages/platforms/orientation/cloud_save
media
leaderboards
purchases/hasProducts
advUsedBlocks
```

The older reverse-engineered `playersCount` field was not present in the tested current responses.

## Rating semantics confirmed

For tested game pages the value in `gqRating` matched the server-rendered label `Рейтинг Яндекс Игр`, while `rating` represented the 1–5 player rating and `ratingCount` the vote count.

For the checked `get_games` batch, the counts in `score[1..5]` summed to `ratingCount`, supporting the interpretation of `score` as the star-vote distribution.

## `__playPageData__` confirmed

The separate `__playPageData__.gameData` object was present on **10/10 checked pages** and exposed additional useful metadata such as:

```text
appVersion
publishedTime
advUsedBlocks.rewarded
advUsedBlocks.fullscreen
settings.adv.sticky
extraFeatures leaderboards/purchases/hasProducts
```

Some pages also exposed counter/goal configuration. Such configuration is metadata only and must not be represented as actual competitor performance.

## Interpretation rules

```text
gqRating            first-party public quality/engagement proxy
rating/ratingCount  player-review signal
feed exposure        contextual observation
sponsored exposure   not organic recommendation evidence
search result count  supply/discovery signal, not competitor count
minLoadTime          Yandex-provided load-time metadata, not our benchmark
```

The observations above are contextual and dated. Future collection must store its own probe context/session/run metadata and must not assume feed composition, search counts, or field presence are invariant.

## What remains unavailable directly

The tested current public data did not directly expose exact competitor:

```text
DAU
sessions/day
D1/D7 retention
average session duration
playtime/player
recommendation impressions
CTR
revenue
ARPDAU
ad impressions
```

These gaps are handled using explicit proxy/evidence semantics rather than pretending they are measured values.
