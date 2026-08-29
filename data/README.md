# Local data directory

Runtime data belongs here and is intentionally ignored by Git.

Expected layout:

```text
data/
  raw/
  normalized/
  reports/
  sessions/
```

Raw snapshots are immutable once written. Never commit collected market data to the repository.

`reports/` is the local destination for empirical analysis artifacts such as taxonomy samples, validated annotation batches, adjudicated gold sets, primary-review reports, and agreement/confusion reports. The `yandex-reaper-taxonomy` CLI creates report files exclusively and refuses to overwrite an existing artifact path; choose a new path for a new execution rather than mutating recorded evidence in place.

After the real diversity sample has been produced, the intended offline Phase 3 artifact chain is:

```text
yandex-reaper-taxonomy validate-annotation-batch SAMPLE BATCH --report VALIDATED_BATCH
yandex-reaper-taxonomy build-gold-set SAMPLE GOLD_DECLARATION BATCH... --report GOLD_SET
yandex-reaper-taxonomy build-primary-validation SAMPLE GOLD_SET REVIEW_DECLARATION --report PRIMARY_REVIEW
yandex-reaper-taxonomy analyze-primary-agreement SAMPLE GOLD_SET BATCH... --report AGREEMENT_REPORT
```

`BATCH...` in agreement analysis must use the exact gold-set source-batch order. Gold-set construction itself verifies exact declared source hashes and derives persisted source order from the declaration. These commands only validate/build artifacts from supplied evidence; they do not generate fake annotation decisions or satisfy any real-data roadmap item on their own.

`sessions/` is operational local state for reusable HTTP profiles. Persistent anonymous profiles may contain raw cookie values required to reuse the same browser-like identity across probes. These files are not analytical evidence: never commit, publish, or share them. Raw snapshots and SQLite provenance must contain only safe session metadata such as the profile label, stable non-secret local profile-instance ID, cookie-state fingerprint, and profile age. The instance ID is cohort provenance for one local persistent profile and is not a Yandex account/user identifier or credential.
