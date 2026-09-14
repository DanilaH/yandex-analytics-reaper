# R0.4-P1 Exact-ID Point Observation — Independent Review — 2026-09-14

## Verdict

**PASS FOR MERGE after review fixes and live validation.**

R0.4-P1 is intentionally narrow: explicit known Yandex IDs become immutable `point_observed` evidence through the existing raw-first `catalogue.get_games` path. It does not alter search/comparable membership, frozen Thesis Intelligence contracts or portfolio decisions.

## Review findings repaired before acceptance

### 1. Create-only output originally failed too late

Initial implementation checked output collision only while writing the ZIP. A repeated command could therefore perform a new network collection and persist a new raw snapshot before discovering that the requested artifact path already existed.

That violates the intended create-only side-effect boundary.

**Fix:** `ListingObservationArtifactCollector.collect()` now refuses an existing artifact path before calling the rich collector. A focused test uses a collector that raises if invoked, proving the overwrite path fails before collection side effects.

### 2. Manifest cohort identity needed an explicit verifier binding

The first verifier bound member hashes, declaration hash and source snapshot identity, but did not separately assert that manifest/report `observation_set_id` + `observation_set_version` equal the declaration identity.

A maliciously rebuilt but internally valid manifest could therefore mislabel the cohort metadata.

**Fix:** offline verification now explicitly binds declaration, manifest and report observation-set identity before accepting the artifact.

### 3. Lint/format cleanup

The initial CI exposed only mechanical Ruff findings after the semantic review: one unused import and line-length/import formatting issues. They were repaired before the clean repository gate.

## Live validation corrected the acceptance assumption

The first live Keycap acceptance assertion incorrectly assumed all three requested IDs must be returned by a successful `catalogue.get_games` call.

That assumption was falsified by the real source on 2026-09-14:

```text
requested = [540402, 559445, 553722]
returned  = [540402, 559445]
missing   = [553722]
unexpected = []
```

Collection itself passed and offline replay verification passed. Only the overly strict acceptance assertion failed.

This was not repaired by weakening evidence integrity or by inventing a zero/deleted status. The acceptance gate was corrected to require exact partition semantics:

```text
returned ∪ missing = requested
returned ∩ missing = ∅
order follows the declaration
unexpected = []
```

`553722` is therefore recorded only as **missing from this exact source response**. This does not prove zero ratings, deletion, unpublishing, platform absence or any other negative status.

This empirical result strengthens the rationale for R0.4: known-listing evidence must preserve source uncertainty rather than silently converting missingness into a market fact.

## Contract review

The implementation preserves the intended boundaries:

- `point_observed` is explicit provenance;
- a point-observed listing does not acquire query/rank/search-union membership;
- exact raw body + raw metadata are packaged into the artifact;
- requested, returned, missing and unexpected IDs remain separate;
- unexpected IDs fail closed;
- the artifact is create-only;
- member order/path/size/SHA-256 are canonical and verified;
- offline verification reparses exact raw bytes through `YandexGetGamesParser` and requires the rebuilt report to equal the packaged report;
- source request context must prove the exact declaration ID order and `format=long`;
- no scheduler, second metadata collector, query-expansion logic or automatic competitor classification was introduced.

## Quality gate

Clean implementation CI run `34841270353` passed:

- Ruff;
- strict mypy;
- pytest + coverage.

Temporary patch/review workflows were removed from the branch before final review.

## Decision

P1 is accepted for merge. The remaining meaningful longitudinal question belongs to P2 and must not be answered by same-day repeated collection presented as market velocity.
