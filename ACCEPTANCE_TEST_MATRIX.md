# ACCEPTANCE_TEST_MATRIX

- **Updated on (UTC):** 2026-04-22
- **Owner:** QA + Platform + Backend + Frontend
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Acceptance release-critical criteria (normalized)

| Criterion ID | Acceptance criterion | Unified status | Concrete evidence (test/workflow/artifact/doc) |
|---|---|---|---|
| RC-004 | Final acceptance bundle fully passing (`overall_status=pass`) | `partial` | Command: `make final-acceptance`; workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; artifact: `artifacts/final_acceptance/summary.json` |
| RC-007 | Replace dry-run/reporting E2E acceptance path | `partial` | Workflow: `.github/workflows/ci.yml`; evidence currently partial in `artifacts/final_acceptance/*.log` |
| RC-008 | PDF conversion reliability acceptance path | `partial` | Workflow: `.github/workflows/ci.yml`; evidence currently partial in `artifacts/final_acceptance/*.log` |
| RC-009 | Approval/sign/archive handoff acceptance path | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; evidence currently partial in `artifacts/final_acceptance/*.log` |
| RC-010 | Workspace hub routes full acceptance behavior | `partial` | Workflow: `.github/workflows/e2e-smoke.yml`; script: `npm --prefix frontend run build`; frontend route tests |
| RC-016 | Critical-path coverage matrix normalization closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; tests/docs listed in `docs/stabilization/PLAN.md` Block B.1 |


| RC-017 | Document generation chain orchestration states + retry semantics (`generated/headers_applied/pdf_ready/handoff_ready/failed/retrying`) | `done` | Backend integration: `backend/tests/test_document_orchestration_state.py`; E2E smoke scenario: `frontend/e2e/key-scenarios.spec.ts` (`quick generation timeline shows orchestration states for chain flow`) |

## Rule to avoid status drift

Release-critical statuses are not authored independently in this file.
Any status change must be applied first in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`, then mirrored here by Criterion ID.

## Cross-links

- Release verdict: `RELEASE_READINESS.md`
- Canonical blockers/checklist/evidence map: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Gap tracker: `GAP_REPORT.md`
- Known constraints: `KNOWN_LIMITATIONS.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`
