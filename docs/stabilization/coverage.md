# Stabilization Coverage Map

_Last updated: 2026-04-19._

This document captures current test/workflow evidence and explicit gaps for stabilization-critical paths.

## Coverage matrix (current state)

| Critical path | Concrete evidence in repo | Current state | Explicit gaps |
|---|---|---|---|
| Tenant isolation on API read/write | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/integration/test_abac_query_isolation.py`, `tests/test_tenant_security.py` | **Partially covered** at integration + unit levels | Need a single marker or CI subset that guarantees these suites always run as a dedicated gate (currently part of broad `pytest`). |
| RBAC/ABAC denial/allow behavior | `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py`, `backend/app/modules/rbac_abac/*` | **Partially covered** | Role-to-endpoint matrix is not maintained in one place; coverage is test-file-distributed. |
| File upload/finalize/storage safety | `tests/test_files_upload.py`, `tests/test_file_storage.py`, `tests/services/test_file_storage_service.py`, `tests/test_files_core_next54.py`, `backend/app/modules/files/*` | **Partially covered** | No explicit negative test inventory linked to each hardening control (macro rejection, AV quarantine behavior, presign misuse). |
| Job/pipeline status transitions | `tests/integration/test_job_status_flow.py`, `tests/integration/test_pipeline_steps_happy_path.py`, `tests/integration/test_pipeline_idempotency.py` | **Partially covered** | No baseline latency/error budget linked to these paths in CI; functional coverage only. |
| Outbox/webhook tenant separation | `tests/integration/test_two_tenant_outbox_webhook_documents.py`, `tests/test_inbound_webhook_tenant_context.py` | **Partially covered** | Need explicit retry/terminal assertion coverage tied to gateway policy doc for release sign-off. |
| Frontend auth and route protections | `frontend/e2e/smoke.spec.ts`, `.github/workflows/e2e-smoke.yml` | **Partially covered** | Critical scenarios are secret-dependent and can be skipped; no hard fail policy for skipped auth/limited-role tests. |
| CI-level quality gates | `.github/workflows/ci.yml`, `scripts/ci/static_gates.sh`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_default_secrets.py` | **Implemented baseline** | No canonical mapping of each stabilization requirement to blocking/non-blocking gate owner. |

## What CI runs today (evidence)

- Backend broad suite: `pytest --junitxml=artifacts/backend-junit.xml` in `.github/workflows/ci.yml`.
- Contract tests: `pytest tests/contract -m contract -v` in `.github/workflows/ci.yml`.
- Frontend CI and coverage-critical gate: `npm --prefix frontend run ci` and `npm --prefix frontend run test:coverage:critical` in `.github/workflows/ci.yml`.
- Optional/scheduled browser smoke: `.github/workflows/e2e-smoke.yml` runs `npm run e2e` in `frontend`.

## Gap list to close

1. Define a dedicated stabilization test selection (e.g., by marker/path list) instead of relying on full-suite inclusion.
2. Add explicit “must-not-skip” policy for credentialed e2e scenarios.
3. Link each acceptance criterion in `docs/stabilization/PLAN.md` to exact tests and workflow jobs.
