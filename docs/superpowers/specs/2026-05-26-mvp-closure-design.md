# MVP Closure — Strategy Design

- **Created:** 2026-05-26 (UTC)
- **Author:** Claude Opus 4.7 (1M context) via `/superpowers:brainstorming` session
- **Status:** Draft → awaiting user approval → writing-plans
- **Approach selected:** C — Workflow-clustered onion-peel (5 iter'ов)
- **Successor doc:** implementation plan (next via `writing-plans` skill)

This is a **strategy spec**, not a code-architecture spec. It defines the ordering of work streams, exit criteria, and risk policy for closing the MVP. The successor implementation plan will translate each iter into concrete PRs with file-level changes.

---

## 1. Scope & exit criteria

### In scope

- **Release blocker closure:**
  - RB-001 → `done` (postgres-minio mode passes acceptance JSON)
  - RB-002 → `done` (perf-baseline manifest published with full endpoint list)
  - RB-005 → `done` (e2e-smoke green: mandatory + credential)
  - RB-003 → `done` (`final_acceptance/summary.json` `overall_status=pass`)
- **`main` CI restoration:** all 3 currently red jobs green
  - `alembic-postgres-upgrade`
  - `perf-smoke`
  - `container-image-scan`
- **App-level defects from `[[app-level-defects-post-billing]]`** items #2, #2b, #3 — closed
- **Doc sync (per Synchronization rule):** 6 docs cascade-updated in fixed order

### Out of scope (deferred to v1.1)

- RC-013 (template scope migration) — `missing`, non-blocking per `KNOWN_LIMITATIONS.md`
- RC-014 (Branch entity separated from `Site`) — `missing`, non-blocking
- RC-011 (Notifications escalation/orchestration) — `missing`, non-blocking
- Deleted unit tests rebuild (5 `tenant-isolation` tests from iter-17b)
- Cohort items `documentversionstatus` + `npabindingtarget` enum drift — not in bootstrap path, defer until surfaced in CI per Session 68 precedent

### Exit criterion (one line)

`RELEASE_READINESS.md` shows `verdict: READY` with date and all 6 RB checkboxes `[x]`.

---

## 2. Workstreams & ordering

### Graph

```
                          ┌────────────────┐
                          │  iter-20       │
                          │  starlette     │
                          │  + FastAPI     │
                          │  upgrade       │
                          │  (parallel)    │
                          └────────┬───────┘
                                   │
   ┌───────────────┐       ┌───────▼────────┐       ┌────────────────┐
   │  iter-18      │       │  main green:   │       │  iter-19       │
   │  RB-002e+f    ├──────►│  alembic-pg ✓  │◄──────┤  RB-001 fixes  │
   │  perf-smoke   │       │  perf-smoke ✓  │       │  restore-drill │
   │  cohort       │       │  cont-scan  ✓  │       │  cohort        │
   └───────────────┘       └───────┬────────┘       └────────────────┘
                                   │
                          ┌────────▼───────┐
                          │  iter-21       │
                          │  Dispatch:     │
                          │  RB-001/002/005│
                          │  workflows     │
                          └────────┬───────┘
                                   │
                          ┌────────▼───────┐
                          │  iter-22       │
                          │  RB-003 close  │
                          │  + 5-doc sync  │
                          └────────────────┘
```

### Dependencies

- iter-18 ⇒ unblocks `alembic-postgres-upgrade` + `perf-smoke`
- iter-19 ⇒ unblocks `restore-drill` postgres-minio mode artifact
- iter-20 ⇒ unblocks `container-image-scan` (independent — can run in parallel with 18/19)
- iter-21 requires ALL of iter-18/19/20 merged to `main`
- iter-22 requires iter-21

### Parallelism rule

iter-20 (starlette + FastAPI upgrade) is the only iter that may proceed in parallel with another. It touches `requirements*.txt`, `pyproject.toml`, `Dockerfile`, and possibly `backend/app/middleware/*.py` — none of which overlap with iter-18 (migrations/scripts) or iter-19 (CI workflow yaml). Parallelization is done via separate worktree.

iter-18 and iter-19 must remain sequential because both may touch `.github/workflows/*.yml`.

### Wall-clock estimate

| Sequencing | Sessions |
|---|---|
| Strict serial (one iter/session) | 5 |
| With iter-20 parallelized via worktree | 4 |

This is 2× faster than Approach A (9 sessions) considered during brainstorming.

---

## 3. Per-iter detail

### iter-18 — RB-002e + RB-002f (perf-smoke cohort)

**Root cause:**

- **RB-002e:** api-1 and beat-1 containers both run `alembic upgrade head` at startup. Race condition → `duplicate key value violates unique constraint "pg_type_typname_nsp_index"` on enum type in `alembic_version` table. See PR #584 `perf-smoke-logs.txt:466`.
- **RB-002f:** `admin.bootstrap.skipped` because admin password is empty in the perf-smoke profile. perf-smoke sends login without credentials → 401 on `/api/v1/dashboard/summary`.

**Probable target files (verify when writing-plans):**

- `docker-compose*.yml` or `docker/entrypoint*.sh` — restrict alembic upgrade to api-1 only (e.g., `if [ "$ROLE" = "api" ]; then alembic upgrade head; fi`), or make alembic upgrade idempotent under concurrency
- `scripts/bootstrap_tenant.py` or `scripts/perf/api_load.py` — locate where admin password remains empty for perf-smoke profile
- `.github/workflows/ci.yml` `perf-smoke` job — env var/secret refs

**Expected PR shape:** ~50-100 lines across 3-4 files. Two pin tests (e.g., `test_alembic_idempotent.py`, `test_perf_smoke_admin_bootstrap.py`) or one integration assertion.

**Validation:** CI on the PR turns `alembic-postgres-upgrade` and `perf-smoke` green.

### iter-19 — RB-001 fixes (restore-drill cohort)

**Root cause:**

- **bitnamilegacy/minio S3 metadata drift:** restore_drill object verifier compares Content-Type / user-metadata / storage-class, which drift in the newer minio release relative to the docker-compose baseline.
- **LibreOffice missing in restore-drill.yml:** `soffice` is not installed in the restore-drill runner, but `backend.app.cli.main health check` requires it (exit code 4).

**Probable target files:**

- `.github/workflows/restore-drill.yml`:
  - (a) pin `bitnamilegacy/minio` to a specific tag matching docker-compose baseline `RELEASE.2024-12-18T13-15-44Z`, OR switch to `minio/minio` via custom Dockerfile
  - (b) add `apt-get install -y libreoffice-core` step (or equivalent for the runner image)
- `scripts/restore_drill.py` `_verify_objects()` — optionally relax to data-hash-only comparison as a fallback (see Risk #3)

**Expected PR shape:** ~30-60 lines in 1-2 workflow/script files.

**Validation:** `restore-drill.yml` run on `postgres-minio` mode returns artifact with `success: true`, `object_mismatches: []`, `smoke_boot.exit_code: 0`.

### iter-20 — starlette + FastAPI upgrade (parallel)

**Root cause:** CVE in starlette below patched version; `container-image-scan` (trivy) red.

**Probable target files:**

- `requirements.txt` / `pyproject.toml` — bump starlette + FastAPI to a compatible pair
- `backend/app/middleware/*.py` — possible breaking API changes (rare on minor versions)
- `backend/tests/test_middleware_*.py` — regression coverage

**Expected PR shape:** dependency bump = 1-2 lines in requirements + possible API adjustments. Worst case: ~5-15 files if FastAPI has breaking changes in the pinned major.

**Predicted complications:** Pydantic version coupling, lifespan API changes, exception_handlers signature.

**Validation:** `container-image-scan` green + all existing tests pass + `.github/security-exceptions.yml` starlette entry removed.

**Parallelization:** runs in a separate worktree. Does not touch migrations or `.github/workflows/*.yml`. Merge order: either BEFORE iter-21 (preferred) or AFTER — never concurrent with iter-21.

### iter-21 — Workflow dispatch + artifact validation

**No code changes.** Actions only:

1. `gh workflow run restore-drill.yml --ref main` (mode=postgres-minio)
2. `gh workflow run perf-baseline.yml --ref main`
3. `gh workflow run e2e-smoke.yml --ref main`
4. Download artifacts, verify acceptance JSON criteria from §5 below

**Validation:** see §5 acceptance evidence table.

**Failure mode:** if any artifact does not meet acceptance criteria, return to the relevant iter (18 or 19) with a specific diagnostic. Do not close the corresponding RB until artifact validates clean. This may surface a new RB-002g / RB-001-g / RB-005-g — legitimate per Risk #2.

### iter-22 — RB-003 closure + 5-doc cascade sync

**No code changes.** Doc-only branch `docs/sync-mvp-closure-rb003-final` from green `main`.

**Doc sequence (per Synchronization rule in `RELEASE_BLOCKERS_STATUS.md`):**

1. `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` — all 6 checkboxes `[x]`, "Updated on (UTC)" refreshed, artifact run URLs linked
2. `RELEASE_READINESS.md` — verdict: **READY**; RC-001/002/006 → `done`
3. `ACCEPTANCE_TEST_MATRIX.md` — RC-004 `partial` → `done` after `final-acceptance/summary.json` refresh
4. `KNOWN_LIMITATIONS.md` — sections "CI stabilization limitations" + (if applicable) "Document chain limitations" archived to "Resolved as of <date>"
5. `GAP_REPORT.md` — Iter-restoration row → `done`, RC-006 → `done`
6. `docs/stabilization/PLAN.md` — final tick
7. `AI_IMPLEMENTATION_REPORT.md` — Session 69+ handoff prepended

**Validation:** `make final-acceptance` green, `final_acceptance/summary.json` `overall_status: pass`, commit + tag `v1.0-RC1` (push deferred to stakeholder approval — not part of this spec).

**Failure mode:** if `make final-acceptance` does not pass after iter-21 acceptance evidence is good, the failure is a `final-acceptance` aggregator bug or a missed RB sub-criterion, not a release blocker re-open. Diagnose against `final_acceptance/summary.json` field-by-field, then ship a follow-up code/script PR (becomes iter-22.5) before doc cascade. Doc cascade does NOT proceed on partial pass.

---

## 4. Risk & rollback

### Top-3 risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | iter-20 starlette upgrade breaks middleware/lifespan API → cascade regressions in test suite | Medium | High | If PR breaks >3 tests files, **fallback to exception extension**: extend `expires_on` in `.github/security-exceptions.yml` to 2026-12-31, defer upgrade to v1.1. This fallback path is explicitly legitimate. |
| 2 | iter-21 dispatch surfaces a new RB-002g / RB-001-g / RB-005-g (latent bug, by analogy with how PR #584 surfaced e/f) | Medium | Medium | Re-loop: add iter-21.5 closing the newly surfaced item, then return to iter-21 dispatch. Precedent: the entire RB-002 a→d chain emerged this way (Session 67 → 68). Not a process failure — expected onion-peel behavior. |
| 3 | iter-19 minio pin — chosen image tag turns out unavailable or itself drifts | Low | Medium | Fallback to `_verify_objects()` relaxation: compare data hash only, document as `KNOWN_LIMITATIONS.md` entry, keep RB-001 closed. |

### Minor risks

- Cohort items `documentversionstatus` / `npabindingtarget` surface in iter-21 dispatch (not deferred — actually fire). Resolution: extend cohort fix inline in iter-18.
- iter-22 doc sync misses a document → release verdict erroneously READY. Mitigation: hard 7-file checklist in iter-22 PR template; CI lint that `RELEASE_READINESS.md` verdict line and `RELEASE_BLOCKERS_STATUS.md` checkbox count are in sync (deferred enhancement, not required for v1.0).

### Rollback policy

- Each iter PR ≤ 100-200 lines → `git revert <merge-sha>` is trivial.
- Does not apply to iter-22 (doc-only) — replace with a new PR carrying corrected state.
- Does not apply to iter-21 (no code) — re-dispatch with the additional fix.

### Not a risk (explicitly)

- "Cycle will never converge" — false. Sessions 64-68 (RB-002 a→d) showed cohort onion-peel converges in ~4 iter'ов per category.
- "Conflicts between iter'ами" — mitigated by hard ordering. Only iter-20 is parallel, and it touches disjoint file sets.

---

## 5. Acceptance evidence & sign-off

### Per-RB acceptance criteria

| RB | Artifact | Source | Acceptance check |
|---|---|---|---|
| RB-001 | `restore-drill-evidence/latest-postgres-minio.json` | GH Actions run after iter-21 dispatch | `success: true` && `restore.verification.counts_match: true` && `documents_checksum_match: true` && `object_content_and_metadata_match: true` && `object_mismatches: []` && `smoke_boot.exit_code: 0` |
| RB-002 | `artifacts/perf/nightly/trend-manifest.json` | GH Actions run after iter-21 dispatch | 6 endpoint records: `/health`, `/api/v1/dashboard/summary`, `/api/v1/templates`, `/api/v1/search/suggest`, `/api/v1/documents/generate`, `/api/v1/files`; each with numeric p50/p95/p99/throughput_rps + `error_rate < 0.01` |
| RB-005 | e2e-smoke job log + `e2e-backend-log-*` (on failure) | GH Actions run after iter-21 dispatch | `Minimal smoke (mandatory)`: PASS; `Credential smoke (bootstrap_local)`: PASS — all 7 rules of access matrix green |
| RB-003 | `artifacts/final_acceptance/summary.json` | `make final-acceptance` locally or in iter-22 CI | `overall_status: pass` |

### Sign-off commit template (iter-22)

```
release: RB-001/RB-002/RB-005 + RB-003 verified — MVP READY as of <ISO date>

- RB-001 restore drill (postgres-minio): success=true, no mismatches
  Evidence: <gh-run-url>
- RB-002 perf baseline: 6/6 endpoint manifest with p50/p95/p99
  Evidence: <gh-run-url>
- RB-005 e2e diagnostics: mandatory + credential both green
  Evidence: <gh-run-url>
- RB-003 final acceptance: overall_status=pass
  Evidence: make final-acceptance local + CI

Release blockers: 6/6 closed
Verdict: READY for v1.0-RC1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Doc cascade sign-off chain

The order is hard — RELEASE_BLOCKERS_STATUS.md is canonical and MUST update first; all other files mirror it.

```
1. RELEASE_BLOCKERS_STATUS.md  (canonical source, MUST be first)
2. RELEASE_READINESS.md         (verdict: READY)
3. ACCEPTANCE_TEST_MATRIX.md    (RC-004 → done)
4. KNOWN_LIMITATIONS.md         (archive resolved sections)
5. GAP_REPORT.md                (Iter-restoration → done)
6. docs/stabilization/PLAN.md   (final tick)
7. AI_IMPLEMENTATION_REPORT.md  (Session 69+ handoff prepended)
```

### Final action after iter-22

- Tag `v1.0-RC1` on the merge commit of iter-22
- Push of the tag to remote is deferred to stakeholder approval — outside this spec

### Explicitly NOT required for sign-off

- Cohort items `documentversionstatus` / `npabindingtarget` enum drift — deferred to v1.1 per Session 68 precedent
- Deleted unit tests (`test_audit_log_isolation`, `test_workflow_events_isolation`, `test_webhook_delivery_isolation`, `test_outbox_isolation`, `test_notification_isolation`) rebuild — deferred to v1.1
- RC-013 / RC-014 / RC-011 missing features — non-blocking per `KNOWN_LIMITATIONS.md` ("Other limitations may remain partial without blocking release if they are not mapped in the release-blocker checklist")

---

## Cross-references

- Canonical blocker source: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Acceptance closure map: `ACCEPTANCE_TEST_MATRIX.md`
- Known limitations: `KNOWN_LIMITATIONS.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`
- Latest session handoff: `AI_IMPLEMENTATION_REPORT.md` (Session 68 at top)
- Cohort knowledge: `[[rb002-enum-migration-cohort]]` memory entry
- App-level defects context: `[[app-level-defects-post-billing]]` memory entry
- Workflow execution reference: `RB_BLOCKERS_EXECUTION_READY.md`
