# Mystery / Unboxing / Collection sweep v1

Permanent compact record of the real Reaper `0.2.0` acceptance/opportunity sweep executed on
2026-09-01.

## Identity

- experiment: `mystery-unboxing-collection-sweep-v1`
- run: `20260901T062453Z`
- workflow: `analyst-experiment-v1.2`
- context: clean anonymous, RU, desktop / desktop_other, 3 pages
- families: 15
- exact queries: 36
- unique comparable listings: 665
- rich metadata: 665 / 665
- final invocation: `resume`, workers=4
- verifier: `pass`

## Recovery acceptance

The first invocation was deliberately killed with `SIGKILL` after completed exact-query evidence
existed. The same workdir was resumed with four workers. The final execution reused 4 valid
completed queries and collected 32 queries, totaling 36. Stale interrupted probe runs were not
reused.

## Research decision

Manual opportunity decomposition is complete.

- **BUILD / route to M2:** `tactile-mystery-collectibles-v1` — original mystery object, short tactile
  unwrap, random rarity reveal, album, duplicate currency.
- **WATCH:** stripped lucky-object / lucky-block reveal + collection.
- **SKIP:** generic case simulator, low-effort pack-opening reskin factory, full Roblox-like
  lucky-block clone.

See [`opportunity-decomposition.md`](opportunity-decomposition.md) for the reasoning and
[`candidate-review.csv`](candidate-review.csv) for the reviewed benchmark set.

## Compact evidence files

- `manifest.json` — exact sweep input.
- `run-summary.json` — run/release/Actions identity and artifact hashes.
- `listings.csv.gz` — gzip-compressed CSV with 665 enriched unique listings from the verified sweep.
- `comparable_memberships.csv.gz` — gzip-compressed family membership + exact-query provenance.
- `search_supply.csv` — query-level Yandex `totalGamesCount` observations.
- `family-coherence.json` — query-family overlap diagnostics.
- `family-summary.csv` — compact market-family features used in manual analysis.
- `candidate-review.csv` — manually reviewed candidate/benchmark evidence.

The full raw snapshots, SQLite database, execution logs and verified immutable ZIP are intentionally
not committed to Git. At closeout they are available as GitHub Actions artifact `9788694982` from
run `33477467946` with 14-day retention. `run-summary.json` preserves the immutable artifact hashes.

## Evidence caution

`ratingCount`, search rank/exposure and current supply are traction/supply proxies, not DAU,
revenue, retention, playtime, CTR or profitability. Query-family labels are analyst hypotheses;
coherence varies materially and broad family averages must not be read as clean market estimates.
