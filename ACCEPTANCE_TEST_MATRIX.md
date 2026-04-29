# ACCEPTANCE_TEST_MATRIX

- **Updated on (UTC):** 2026-04-30
- **Owner:** QA + Platform + Backend + Frontend
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

## Acceptance release-critical criteria (normalized)

| Criterion ID | Acceptance criterion | Unified status | Concrete evidence (test/workflow/artifact/doc) |
|---|---|---|---|
| RC-004 | Final acceptance bundle fully passing (`overall_status=pass`) | `partial` | Command: `make final-acceptance`; workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; artifact: `artifacts/final_acceptance/summary.json` |
| RC-007 | Replace dry-run/reporting E2E acceptance path | `done` | Tests: `tests/test_replace_api.py`, `tests/test_replace_engine_advanced.py`, `tests/test_pipeline_profile_graph_and_api.py`; workflow: `.github/workflows/ci.yml` (`backend-tests`, `openapi-contract`); artifacts: `backend-test-report` (`artifacts/backend-junit.xml`, `artifacts/coverage.xml`, `artifacts/coverage.json`). |
| RC-008 | PDF conversion reliability acceptance path | `done` | Tests: `tests/test_documents_generate.py`, `tests/pdf/test_api_idempotency.py`, `tests/test_services_pdf_unit.py`; workflow: `.github/workflows/ci.yml` (`backend-tests`); artifacts: `backend-test-report` (`artifacts/backend-junit.xml`, `artifacts/coverage.xml`, `artifacts/coverage.json`). |
| RC-009 | Approval/sign/archive handoff acceptance path | `done` | Tests: `backend/tests/test_approval_signing_v1_error_contract.py`, `backend/tests/test_approval_orchestration_error_contract.py`, `backend/tests/test_next57_approval_sign_edo_services.py`; workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; artifacts: `backend-test-report`, optional `e2e-backend-log-*` on failure. |
| RC-010 | Workspace hub routes full acceptance behavior | `done` | Tests: `frontend/e2e/smoke.spec.ts` (`attention hub route redirects...`, `limited user denied on attention hub...`); workflow: `.github/workflows/e2e-smoke.yml` (`playwright-smoke-minimal`, `playwright-smoke-credential`); artifacts: Playwright run logs + `e2e-backend-log-*` on failure. |
| RC-016 | Critical-path coverage matrix normalization closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; tests/docs listed in `docs/stabilization/PLAN.md` Block B.1 |


| RC-017 | Document generation chain orchestration states + retry semantics (`generated/headers_applied/pdf_ready/handoff_ready/failed/retrying`) | `done` | Backend integration: `backend/tests/test_document_orchestration_state.py`; E2E smoke scenario: `frontend/e2e/key-scenarios.spec.ts` (`quick generation timeline shows orchestration states for chain flow`) |

## Rule to avoid status drift

Release-critical statuses are not authored independently in this file.
Any status change must be applied first in `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`, then mirrored here by Criterion ID.

## Cross-links

- Release verdict: `RELEASE_READINESS.md`
- Canonical blockers/checklist/evidence map: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Acceptance traceability map: `docs/stabilization/acceptance-traceability.md`
- Gap tracker: `GAP_REPORT.md`
- Known constraints: `KNOWN_LIMITATIONS.md`
- Stabilization tracker: `docs/stabilization/PLAN.md`
