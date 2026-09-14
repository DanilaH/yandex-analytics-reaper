# Durable Evidence Archive — Live Migration Acceptance — 2026-09-14

**Milestone:** `R0.3.1`  
**Implementation PR:** `#63` — `Add durable archive for longitudinal Reaper evidence`  
**Merge commit:** `5ba1233d19865863bfe494a6ee2a97167500aa8e`  
**Live archive workflow:** GitHub Actions run `34828794788` / `Durable evidence archive` run `#1`  
**Acceptance status:** **PASS — LIVE MIGRATION COMPLETE**

This record closes the live-only acceptance work that could not be performed honestly before the archive implementation was merged to `main`.

---

## Post-merge gates

The merge triggered both the ordinary repository quality workflow and the new side-effecting archive workflow.

### Main-branch quality gate

GitHub Actions run `34828794531` / CI run `#354` completed successfully.

The complete `quality` job passed:

```text
ruff check .                                  PASS
mypy src                                      PASS
pytest --cov=yandex_analytics_reaper          PASS
coverage threshold                            PASS
```

This confirms the merged `main` state remained green after PR `#63` landed.

### Durable archive live gate

GitHub Actions run `34828794788` completed successfully. The `archive` job's reconciliation step passed for the complete four-request catalog.

Catalog preflight reported:

```text
request_count = 4
status = pass

trend-mechanics-round2-2026-09-13
trend-mechanics-round3-2026-09-13
trend-mechanics-round4-2026-09-13
trend-mechanics-round5-2026-09-13
```

For every request the workflow performed the intended live path:

```text
resolve exact Actions metadata
→ download exact Actions wrapper ZIP
→ verify committed SHA-256 + size
→ build deterministic member manifest
→ create draft Release at historical producing commit
→ upload wrapper + manifest + checksum
→ redownload all three Release assets
→ verify request + manifest + wrapper
→ sha256sum -c PASS
→ publish Release
```

No identity check had to be weakened during live publication.

---

## Published durable archives

| Archive | Historical target commit | Wrapper size | Wrapper SHA-256 | Members | Manifest content hash |
| --- | --- | ---: | --- | ---: | --- |
| `trend-mechanics-round2-2026-09-13` | `4bf9ae8fa469b4a2c9895ad7c20d9c888ddca0c4` | 13,250,310 | `3dc0026bf18bed4df21cec52570e1c73704dde70a1744abf2098eca52277b0a3` | 3 | `b6ece7ff3480553fb60a6f611b0d1329b5d9933dda2a6b5e6730b08fb15caac2` |
| `trend-mechanics-round3-2026-09-13` | `36ffe25077bb18b138641f8ffdf4c5a8d2d6b846` | 7,113,491 | `17992550ea66d6be41f9518eba710ddbee8870d267e10f16e64efd9621291fac` | 3 | `e841998cb293c052bdc3846313603e64a2f482be2349e7fd1cbd1788e8545ae4` |
| `trend-mechanics-round4-2026-09-13` | `e87a25675ef1596f144b5c3e6e8b7d03c697d014` | 3,995,624 | `078f8d0463d43f85d6b230fec86f0a2b94e4c71c976df45fb87429fd624477a6` | 3 | `ef4a1cbd644a8d5117b7c1d65428892a10f95147231313c62f5fc949a513668a` |
| `trend-mechanics-round5-2026-09-13` | `96d88ee5bb7b945eb30d8b069c14b6060fa00891` | 3,439,722 | `b3e2a1d26d310728af13e5141d8bbc9c69e2e9e3573ed5d74fe086e085882a51` | 3 | `9675afc0b7a0b70707a4558b265d640c5610b1b0808d34e9114a49c34cf26203` |

Every wrapper checksum above is the same SHA-256 bound in the committed archive request and the source GitHub Actions artifact metadata.

Each published Release contains exactly the intended three durable assets:

```text
<archive>.actions.zip
<archive>.manifest.json
<archive>.sha256
```

The workflow redownloaded those assets before publication and the archive verifier returned `status = pass`; `sha256sum -c` also returned `OK` for each wrapper.

---

## Release publication results

Final tags:

```text
evidence-2026-09-13-trend-mechanics-r2
evidence-2026-09-13-trend-mechanics-r3
evidence-2026-09-13-trend-mechanics-r4
evidence-2026-09-13-trend-mechanics-r5
```

They target the historical commits that produced the evidence rather than the later archival implementation commit.

Published UTC times from the live run:

```text
r2  2026-09-14T09:35:58Z
r3  2026-09-14T09:36:09Z
r4  2026-09-14T09:36:20Z
r5  2026-09-14T09:36:31Z
```

The Releases are no longer drafts.

---

## Platform immutability observation

GitHub's Release API reports:

```text
immutable = false
```

for the published migration Releases. Repository-level immutable releases therefore are **not** currently providing an additional platform-enforced immutability layer.

This does not invalidate the archive contract because the implementation deliberately does not depend on that optional repository setting. Evidence integrity remains enforced by:

```text
committed create-only request identity
+ exact historical source provenance
+ wrapper SHA-256 + size binding
+ deterministic member SHA-256 inventory
+ create-only/no-clobber reconciliation
+ redownload verification before publication
+ future request-bound verification on retrieval
```

Enabling GitHub immutable releases later would be defense in depth, not a prerequisite for evidence validity.

---

## Non-blocking runner noise

After the archive work itself completed, `actions/setup-python` reported that it could not reserve its pip cache key because another job was creating the same cache.

That message occurred during post-job cache cleanup. The archive job conclusion remained `success`, all four Releases had already passed their redownload/integrity gates, and no evidence output depends on the pip cache. It is therefore operational noise rather than an archive failure.

---

## Acceptance decision

**R0.3.1 is COMPLETE.**

The original durability defect is closed:

- the four Sep-13 evidence wrappers no longer depend solely on 30-day Actions retention;
- exact source bytes are now durably addressable through published Release tags;
- wrapper and inner-member identities are hash-bound;
- historical experiment ZIPs can be recovered for the existing `yandex-reaper-thesis --prior <zip>` path without changing Thesis Intelligence semantics;
- the implementation and documentation passed independent pre-merge review and live post-merge verification.

No scheduler, database, object-storage abstraction, remote history service or new analytical model is justified by this migration. The next primary product path remains `P2 cheapest credible build/release probe`.
