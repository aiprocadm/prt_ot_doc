# Release-Critical Acceptance Traceability

- **Updated on (UTC):** 2026-04-23
- **Owner:** QA + Backend + Frontend + Platform
- **Purpose:** canonical mapping of release-critical user paths to concrete tests, CI workflow jobs, and produced artifacts.

## 1) Prioritized coverage focus (stabilization order)

Priority is aligned to release risk and user-facing impact:

1. `auth/session`
2. `rbac_abac`
3. `files`
4. `tenant isolation`
5. `document orchestration`
6. `landing/protected routes`

## 2) Traceability map: user path → tests → CI jobs → artifacts

| Release-critical user path | Priority module(s) | Evidence tests (source of truth) | CI workflow jobs | Produced artifacts / logs |
|---|---|---|---|---|
| Login + session establishment + session failure UX | `auth/session` | `tests/test_auth_login.py`, `tests/test_auth_tenant_header_enforcement.py`, `frontend/e2e/smoke.spec.ts` (`login wrong password shows inline error`, `R11 login happy path`) | `.github/workflows/ci.yml` → `backend-tests`; `.github/workflows/e2e-smoke.yml` → `playwright-smoke-credential` | `backend-test-report` (`artifacts/backend-junit.xml`, coverage reports); Playwright logs |
| Protected routes / landing behavior for logged-out users | `landing/protected routes` | `frontend/e2e/smoke.spec.ts` (`protected route redirects to login when logged out`, `attention hub route redirects to login when logged out`) | `.github/workflows/e2e-smoke.yml` → `playwright-smoke-minimal` | Playwright logs (mandatory no-creds subset) |
| Access-denied behavior for limited user roles | `rbac_abac`, `landing/protected routes` | `tests/test_rbac_abac.py`, `tests/unit/test_policy_engine.py`, `frontend/e2e/smoke.spec.ts` (`R12 limited user denied on documents route`, `limited user denied on attention hub...`) | `.github/workflows/ci.yml` → `backend-tests`; `.github/workflows/e2e-smoke.yml` → `playwright-smoke-credential` | `backend-test-report`; Playwright logs |
| Tenant boundary and scoped query isolation | `tenant isolation`, `rbac_abac` | `tests/test_tenant_security.py`, `tests/test_middleware_tenant.py`, `tests/integration/test_tenant_isolation.py`, `tests/integration/test_abac_query_isolation.py` | `.github/workflows/ci.yml` → `lint-and-static` (scoped-query guard), `backend-tests` | `backend-test-report`; static gate logs |
| Files upload/download authorization and signed URL safety | `files`, `tenant isolation`, `rbac_abac` | `tests/test_files_access_parity.py`, `tests/test_files_upload.py`, `tests/test_files_bus_service.py`, `tests/services/test_file_storage_service.py` | `.github/workflows/ci.yml` → `backend-tests` | `backend-test-report` + coverage artifacts |
| Replace dry-run/diff/apply/reporting path | `document orchestration`, `files` | `tests/test_replace_api.py`, `tests/test_replace_engine_advanced.py`, `tests/test_pipeline_profile_graph_and_api.py`, `tests/test_router_parsers.py` | `.github/workflows/ci.yml` → `backend-tests`, `openapi-contract` | `backend-test-report`; contract job logs |
| PDF generation reliability path | `document orchestration`, `files` | `tests/test_documents_generate.py`, `tests/pdf/test_api_idempotency.py`, `tests/test_services_pdf_unit.py` | `.github/workflows/ci.yml` → `backend-tests` | `backend-test-report`; coverage artifacts |
| Approval/sign/archive handoff path | `document orchestration`, `rbac_abac`, `tenant isolation` | `backend/tests/test_approval_signing_v1_error_contract.py`, `backend/tests/test_approval_orchestration_error_contract.py`, `backend/tests/test_next57_approval_sign_edo_services.py` | `.github/workflows/ci.yml` → `backend-tests`; `.github/workflows/e2e-smoke.yml` (cross-checking role-access shells) | `backend-test-report`; `e2e-backend-log-*` on failure |
| Workspace routes (attention hub/task flow surface) | `landing/protected routes`, `rbac_abac`, `tenant isolation` | `frontend/e2e/smoke.spec.ts` (workspace attention redirects + limited-user denied), `backend/app/api/routes/workspace.py` route coverage in backend suite | `.github/workflows/e2e-smoke.yml` + `.github/workflows/ci.yml` (`backend-tests`) | Playwright logs; backend junit/coverage artifacts |

## 3) Credential independence of smoke (must remain true)

`e2e-smoke` is intentionally split into:

- **Mandatory credential-independent smoke:** `playwright-smoke-minimal` with grep `mandatory (no external creds)`.
- **Credential flow matrix:** `playwright-smoke-credential` with `credential_source=[bootstrap_local, repo_secrets]`.

Release policy for stabilization: the smoke baseline **must remain executable via `bootstrap_local`** without required external secrets. `repo_secrets` path is additive and gated by secret availability.

## 4) Artifacts expected for release evidence bundle

Minimum expected evidence references:

- `backend-test-report` artifact:
  - `artifacts/backend-junit.xml`
  - `artifacts/coverage.xml`
  - `artifacts/coverage.json`
  - `artifacts/coverage-term-missing.txt`
- E2E logs from `.github/workflows/e2e-smoke.yml` runs.
- `e2e-backend-log-bootstrap_local` / `e2e-backend-log-repo_secrets` artifacts on failure paths.

## 5) Related source documents

- `ACCEPTANCE_TEST_MATRIX.md`
- `docs/stabilization/coverage.md`
- `docs/TESTING.md`
- `.github/workflows/ci.yml`
- `.github/workflows/e2e-smoke.yml`
