# KNOWN_LIMITATIONS

- **Updated on (UTC):** 2026-05-21
- **Owner:** Product Engineering + Platform
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- **Canonical TZ:** `docs/spec/TZ_FULL_UNIFIED.md` (раздел A — MVP, B — vNext)

## Release-critical limitations subset

| Criterion ID | Limitation tied to release readiness | Unified status | Evidence |
|---|---|---|---|
| RC-011 | Notifications escalation/provider orchestration is not feature-complete | `missing` | Tests: `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py`; workflow: `.github/workflows/ci.yml`; tracker: `GAP_REPORT.md` |
| RC-007 | Replace dry-run/reporting path is incomplete end-to-end | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests: `test_replace_api.py`, `test_replace_engine_advanced.py`); workflow: `.github/workflows/ci.yml` (`backend-tests`, `openapi-contract`); closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |
| RC-008 | PDF conversion acceptance reliability not fully closed | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests: `test_documents_generate.py`, `test_pdf_idempotency.py`, `test_services_pdf_unit.py`); workflow: `.github/workflows/ci.yml` (`backend-tests`); closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |
| RC-009 | Approval/sign/archive handoff acceptance is incomplete | `done` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md` (tests in `test_approval_*.py`, `test_next57_approval_*.py`); workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; closed 2026-04-30 per `RELEASE_BLOCKERS_STATUS.md`. |

## Non-blocking limitations

Other limitations may remain `partial` without blocking release if they are not mapped in the release-blocker checklist.
See canonical mapping in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.

## Cross-links

- Release verdict: `RELEASE_READINESS.md`
- Acceptance map: `ACCEPTANCE_TEST_MATRIX.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`

## Document chain limitations (updated 2026-04-30)
- End-to-end chain state model is unified (`generated → headers_applied → pdf_ready → handoff_ready`), but legacy single-run flow still performs headers/pdf as logical orchestration milestones without a dedicated persisted artifact per milestone.
- Quick-generate timeline currently visualizes orchestration states from task metadata only; historical runs created before 2026-04-22 may not include complete timeline arrays.

## CI stabilization limitations (added 2026-05-21, post-billing-restore)

GitHub Actions billing was restored on 2026-05-21 after a ~9-week block (from 2026-03-21). Eight iterations of fixes (PRs #549–#555) closed most of the surfaced rot but **three `main` CI jobs remain red** after the iter-8 merge:

- **`alembic-postgres-upgrade`** — `DuplicateObjectError: type "<enum_name>" already exists` on Postgres upgrade. Root cause: SQLAlchemy `sa.Enum(...)` emits an extra `CREATE TYPE` after an earlier explicit `postgresql.ENUM(...).create(checkfirst=True)`. PR #555 fixed 7 migrations using `postgresql.ENUM(..., create_type=False)`; additional migrations with the same pattern are suspected (iter-9 candidate). Until this is green, **no release-blocker workflow re-validation can succeed** because backend boot fails.
- **`perf-smoke`** — fails for the same reason transitively (smoke boot requires migrations to apply).
- **`container-image-scan`** — flagged CVE remediation is pending hardening PR (starlette upgrade cross-cuts FastAPI pin); temporary exception is recorded in `.github/security-exceptions.yml` (owner `reviewers-platform-infra`, `expires_on 2026-08-31`), with edge-proxy compensating control documented.

**Release-blocker workflows pending re-validation against post-iter-8 main:**

| Workflow | Maps to | Last known result | Pending action |
|---|---|---|---|
| `.github/workflows/restore-drill.yml` | RB-001 | sqlite-mode green ([run 26215954984](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26215954984)) on `fix/ci-workflows-billing-restore` (pre-iter-8); postgres-minio mode `failure` | Re-trigger against `main` once `alembic-postgres-upgrade` is green |
| `.github/workflows/perf-baseline.yml` | RB-002 | `failure` on pre-iter-8 commits | Re-trigger against `main` once boot is green |
| `.github/workflows/e2e-smoke.yml` | RB-005 | `failure` on pre-iter-8 commits | Re-trigger against `main` once boot is green and frontend `/no-access` regression is verified resolved by iter-8 |

This limitation block exists to make explicit that the release-blocker checkbox states `[ ]` in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` are **not yet stale** — they accurately reflect the absence of post-iter-8 green evidence.
