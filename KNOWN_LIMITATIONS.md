# KNOWN_LIMITATIONS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Product Engineering + Platform
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Release-critical limitations subset

| Criterion ID | Limitation tied to release readiness | Unified status | Evidence |
|---|---|---|---|
| RC-011 | Notifications escalation/provider orchestration is not feature-complete | `missing` | Tests: `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py`; workflow: `.github/workflows/ci.yml`; tracker: `GAP_REPORT.md` |
| RC-007 | Replace dry-run/reporting path is incomplete end-to-end | `partial` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md`; artifact stream: `artifacts/final_acceptance/*.log` |
| RC-008 | PDF conversion acceptance reliability not fully closed | `partial` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md`; artifact stream: `artifacts/final_acceptance/*.log` |
| RC-009 | Approval/sign/archive handoff acceptance is incomplete | `partial` | Acceptance evidence in `ACCEPTANCE_TEST_MATRIX.md`; workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` |

## Non-blocking limitations

Other limitations may remain `partial` without blocking release if they are not mapped in the release-blocker checklist.
See canonical mapping in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.

## Cross-links

- Release verdict: `RELEASE_READINESS.md`
- Acceptance map: `ACCEPTANCE_TEST_MATRIX.md`
- Gap tracker: `GAP_REPORT.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`
