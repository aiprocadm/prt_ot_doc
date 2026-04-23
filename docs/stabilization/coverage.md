# Stabilization Coverage Gates

- **Updated on (UTC):** 2026-04-23
- **Owner:** QA Automation + Backend
- **Canonical status vocabulary:** `done` / `partial` / `missing`

This document defines backend line + branch coverage policy used for CI non-regression gating.

## Static analysis staged expansion (mypy)

- **Gate script:** `scripts/ci/static_gates.sh`
- **Mode:** `--follow-imports=skip` (temporary while staged scope is widened without muting real errors)
- **Current staged scope (wave 1, 2026-04-22):**
  - Tenant guard baseline: `backend/app/db/tenant_row_guard.py`, `backend/app/api/tenant_row_http.py`
  - API slice for file/authz-sensitive path: `backend/app/api/routes/files.py`
  - Middleware slice: `backend/app/middleware/{tenant.py,billing_guard.py,global_error_handler.py,observability.py}`
  - Worker/task slice (legacy + celery): `backend/app/tasks/{__init__.py,_core.py}`, `backend/app/tasks_replace.py`, `backend/app/celery/tasks/{document_jobs_required.py,job_steps.py}`
  - File/authz-sensitive domain: `backend/app/modules/files/service.py`, `backend/app/modules/rbac_abac/query_filters.py`

### Static typing error budget

| Date (UTC) | Scope size (files) | Error budget | Actual mypy errors | Status |
|---|---:|---:|---:|---|
| 2026-04-22 | 14 | 0 | 0 | `passing` |

Notes:
- `backend/app/tasks.py` is not present in this repository; staged checks cover the active task entrypoints in `backend/app/tasks/`, `backend/app/tasks_replace.py`, and celery task modules.
- Budget policy for staged gates remains **zero new errors**; scope expansion happens by adding focused paths and fixing surfaced issues before merge.

## Coverage gate status

| Coverage claim | Status | Partial/missing reason | Exact command/workflow | Artifact path(s) | Evidence links |
|---|---|---|---|---|---|
| Coverage regression gate is enforced | `done` | — | `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`; workflow: `.github/workflows/ci.yml` (`backend-tests`). | `artifacts/coverage.json`, `artifacts/coverage.xml`, `artifacts/coverage-term-missing.txt`; CI artifact: `backend-test-report`. | `.github/workflows/ci.yml`, `scripts/ci/check_backend_coverage_baseline.py`, `docs/stabilization/backend_coverage_baseline.json` |
| Critical-path traceability across unit/integration/e2e is complete | `partial` | Cross-layer mapping exists but not all acceptance scenarios are fully `done` in matrix (notably performance and some workflow edges). | Supporting suites: `./scripts/pytest.sh tests/e2e/final_regression/test_final_regression_api.py` and frontend smoke in `.github/workflows/e2e-smoke.yml`. | CI artifacts split across backend + e2e runs; no single consolidated traceability artifact yet. | `ACCEPTANCE_TEST_MATRIX.md`, `docs/TESTING.md`, `.github/workflows/e2e-smoke.yml` |
| E2E smoke remains credential-independent for mandatory baseline (`bootstrap_local`) | `done` | Mandatory smoke is isolated from external secrets and credential stage includes deterministic local bootstrap path. | Workflow: `.github/workflows/e2e-smoke.yml` (`playwright-smoke-minimal` + `playwright-smoke-credential` matrix `bootstrap_local, repo_secrets`). | Playwright logs; `e2e-backend-log-*` uploaded on failure for credential stage. | `.github/workflows/e2e-smoke.yml`, `frontend/e2e/smoke.spec.ts`, `docs/stabilization/acceptance-traceability.md` |

Release decision is governed by the **single go/no-go checklist** in `RELEASE_READINESS.md`.


## Prioritized stabilization coverage focus

Current ordered focus for coverage expansion and regression protection:

1. `auth/session`
2. `rbac_abac`
3. `files`
4. `tenant isolation`
5. `document orchestration`
6. `landing/protected routes`

Detailed user-path traceability (tests ↔ jobs ↔ artifacts) is maintained in `docs/stabilization/acceptance-traceability.md`.

## What is enforced in CI

The `backend-tests` job in `.github/workflows/ci.yml`:
1. Runs `pytest` with line + branch coverage.
2. Exports `artifacts/coverage.xml`, `artifacts/coverage.json`, `artifacts/coverage-term-missing.txt`.
3. Runs `scripts/ci/check_backend_coverage_baseline.py` and fails on regression.

## Baseline source

Baseline thresholds are committed in `docs/stabilization/backend_coverage_baseline.json` (baseline date: 2026-04-19).

| Scope | Line % (min) | Branch % (min) |
|---|---:|---:|
| overall backend/app | 47.0 | 36.0 |
| auth | 65.5 | 49.4 |
| rbac_abac | 66.2 | 46.3 |
| tenancy | 72.2 | 57.8 |
| files | 55.7 | 39.6 |
| jobs_outbox | 31.9 | 31.5 |

## Deterministic local/CI check

```bash
python scripts/ci/check_backend_coverage_baseline.py \
  --coverage-json artifacts/coverage.json \
  --baseline docs/stabilization/backend_coverage_baseline.json
```

## Cross-links

- Plan tracker: `docs/stabilization/PLAN.md`
- Acceptance scenarios: `ACCEPTANCE_TEST_MATRIX.md`
- Gap log: `GAP_REPORT.md`
- Release verdict: `RELEASE_READINESS.md`
- Accepted constraints: `KNOWN_LIMITATIONS.md`

## Static typing staged gate (incremental expansion)

- **Last expanded (UTC):** 2026-04-22
- **Runner:** `scripts/ci/static_gates.sh`
- **Mode:** `mypy --follow-imports=skip` (temporary while broad API typing debt is reduced)

### Current staged scope

1. Tenant-row guard baselines:
   - `backend/app/db/tenant_row_guard.py`
   - `backend/app/api/tenant_row_http.py`
2. Middleware:
   - `backend/app/middleware`
3. Worker/task paths:
   - `backend/app/tasks`
   - `backend/app/celery/tasks`
   - `backend/app/services/tasks.py`
4. API slices + file/authz-sensitive modules:
   - `backend/app/api/routes/tasks.py`
   - `backend/app/api/routes/files.py`
   - `backend/app/api/routes/admin_authz.py`

### Error budget tracking

| Date (UTC) | Scope command | Allowed mypy errors | Actual |
|---|---|---:|---:|
| 2026-04-22 | `scripts/ci/static_gates.sh` staged targets | 0 | 0 |

> Notes:
> - Keep introducing narrow, high-risk modules (tenant/authz/files/tasks) before widening to all `backend/app/api`.
> - Do **not** add blanket `ignore_errors`; prefer targeted fixes and test coverage for exposed guard paths.
