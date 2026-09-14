# R0.4 Evidence Completeness — Independent Plan Review — 2026-09-14

## Verdict

**PASS FOR ROADMAP MERGE after scope correction.**

The first improvement brainstorm was directionally right but contained one material duplication risk and two infrastructure risks. The reviewed plan removes them before implementation.

## Evidence that triggered the milestone

Recent live use produced two concrete gaps rather than hypothetical architecture wishes:

1. The Sep-14 Keycap run missed known direct listing `553722` from the bounded search union even when an exact-title query was added. A point `catalogue.get_games` observation recovered it successfully.
2. External/app-store/trend/visual evidence that materially affects analyst interpretation is currently preserved mostly in prose/research notes rather than one hash-bound supplemental package.

These are evidence-quality defects worth addressing because they directly change how confidently a thesis can be evaluated.

## Review corrections

### 1. Removed: new generic rich-metadata enrichment layer

Initial idea: add a deep-enrichment stage after search.

Review result: **duplicate existing capability**.

The analyst runner already enriches search-derived listings, and `YandexRichMetadataCollector` already provides a raw-first, schema-guarded, normalized exact-ID `get_games` collection seam.

Correction: R0.4 P1 reuses that collector to produce an immutable point-observation artifact. No second parser/client/normalizer path.

### 2. Removed: query expansion as the solution to recall

The Keycap case falsified the assumption that more exact/synonym queries guarantee retrieval of an already-known listing.

Correction: search remains discovery evidence. Known decision-relevant IDs receive a separate `point_observed` channel. Point observations do not alter historical search-union membership or supply counts.

### 3. Deferred: scheduler / daemon

Regular watch is useful, but scheduling before the observation artifact is accepted would stabilize the wrong layer first and contradict the existing roadmap bias against infrastructure sophistication.

Correction: P1/P2 accept explicit observation artifacts first. Scheduling is an optional later milestone only after real longitudinal acceptance.

### 4. Removed: visual classifier / automatic qualitative scoring

Visual/gameplay/review-contamination judgments are useful, but an ML/LLM classifier would turn bounded human evidence into an opaque score and add maintenance cost without demonstrated calibration.

Correction: preserve these as typed analyst annotations inside the supplemental evidence bundle.

### 5. Strengthened: external evidence durability

A URL alone is mutable and cannot honestly serve as immutable proof.

Correction: attached bytes receive exact SHA-256/size identity. URL-only evidence is explicitly `reference_only` and remains weaker.

### 6. Strengthened: requested vs returned exact IDs

`get_games` success must not imply every requested listing was returned.

Correction: point artifacts preserve requested, returned, missing and unexpected IDs independently. Missing is missing evidence, never zero/unpublished/deleted.

### 7. Preserved: frozen 0.3 contracts

R0.3 Thesis Intelligence has already passed real-data validation and durable-archive migration. Mutating `thesis-intelligence-method-v1` or `thesis-intelligence-build-inputs-v1` would make historical rebuild semantics harder to reason about.

Correction: R0.4 adds separate immutable artifacts and later binds them through a new evidence-pack envelope.

## Scope-creep check

The reviewed milestone does **not** include:

- a generic web crawler;
- app-store/Pinterest connectors before a manual bundle proves the schema useful;
- automatic opportunity scoring;
- production-burden estimation;
- a dashboard;
- cross-platform matching;
- a generic job scheduler;
- a rewrite of search/comparables;
- a rewrite of the experiment runner.

This keeps R0.4 tied to observed analyst friction rather than infrastructure possibility.

## Sequencing decision

Approved sequence:

1. **P0 — contract freeze + review**: additive provenance/evidence semantics.
2. **P1 — exact-ID point observation**: immutable `get_games` artifact using existing collection seams.
3. **P2 — longitudinal known-ID comparison**: true repeated frozen observations, no fake short-window velocity.
4. **P3 — supplemental evidence bundle**: external/manual evidence with attachment hashes and explicit `reference_only` downgrade.
5. **P4 — thesis evidence pack**: bind old Thesis Intelligence + new evidence without modifying old artifacts.
6. **P5 — live validation**: Keycap exact-ID control, Decorated Mail supplemental control, then one repeated Keycap point observation.
7. **Later only if justified**: bounded scheduled watch.

## Measurement-honesty invariants

Before implementation, the following are mandatory:

- search absence is not platform absence;
- point-observed IDs do not inflate search supply;
- rating-count delta is only computed between actual frozen observations;
- negative/revised values remain visible;
- external evidence never masquerades as Yandex first-party evidence;
- analyst qualitative annotations are labeled as judgments;
- no automatic BUILD/WATCH/SKIP is introduced.

## Decision

Proceed with the roadmap update and then implement P1 if repository diff/CI review exposes no new blocker.
