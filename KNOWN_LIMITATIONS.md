# KNOWN_LIMITATIONS

- **Updated on (UTC):** 2026-05-04
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
