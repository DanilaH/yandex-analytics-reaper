# R0.4-P1 Exact-ID Point Observation — Live Validation — 2026-09-14

## Acceptance status

**PASS.**

The exact-ID point-observation implementation passed the full repository quality gate and a real Yandex `catalogue.get_games` control using the known Keycap cohort.

## Implementation quality gate

Clean CI run: `34841270353`.

Result:

- Ruff — PASS;
- strict mypy — PASS;
- pytest + coverage — PASS.

## Live Keycap control

Live validation run: `34841547344`.

Declaration:

```text
observation_set_id = keycap-known-direct
observation_set_version = 1
requested IDs = [540402, 559445, 553722]
source = catalogue.get_games
```

The collection command and a separate offline `verify` command produced the same verification result:

```text
status = pass
artifact_sha256 = ae5bd96dca5485f447eb556d3acc5328d18e0fea402c3324efdef3ee1a082a3f
manifest_content_hash = b9761b69210f1fdb689d56be99d411ba7821d4add560c6da7b93307dde837079
source_snapshot_id = 20260914T120606948988Z-071de0c951
requested_count = 3
returned_count = 2
missing_count = 1
```

Observed source partition:

```text
requested = [540402, 559445, 553722]
returned  = [540402, 559445]
missing   = [553722]
unexpected = []
```

Returned listing facts at this observation:

```text
540402 — Эволюция Клавиатуры — rating_count 29 — first_published 1784882674
559445 — Прокачай Клавиатуру — rating_count 25 — first_published 1786030948
553722 — missing from this exact source response
```

The `553722` result is deliberately not interpreted as `rating_count = 0`, deleted, unpublished or absent from Yandex Games. Earlier research successfully point-observed that ID; the current source omission is exactly the kind of mutable-source uncertainty the new artifact must preserve.

## CI transport artifact

GitHub Actions uploaded the validation package as:

```text
artifact ID = 10346401822
name = keycap-known-direct-point-observation-2026-09-14
outer Actions artifact ZIP size = 8529 bytes
outer Actions artifact digest = sha256:aaa2c6b4e4b1d43def770485c544d5f2b6aa51770fcc1280e5e58d45544508bd
```

The outer Actions artifact digest is transport identity and is distinct from the inner self-contained point-observation ZIP SHA-256 `ae5bd96d...`.

## Acceptance interpretation

P1 proves that Reaper can now:

- request a stable explicit known-ID cohort without rediscovering it through search;
- preserve successful returns and source omissions separately;
- freeze exact raw evidence and normalized point facts together;
- verify the artifact fully offline;
- keep point evidence separate from historical search-union membership.

The live control does **not** claim that `553722` was observed successfully on this run. Instead it validates the stronger and more honest contract: a requested known ID that the current source omits remains explicit missing evidence rather than being silently dropped or coerced into a negative market fact.

## Next gate

R0.4-P2 may implement comparison semantics now, but real longitudinal acceptance requires a second observation after a meaningful interval. Same-day repetition must not be presented as current market velocity.
