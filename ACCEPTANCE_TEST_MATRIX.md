# ACCEPTANCE_TEST_MATRIX

- **Updated on (UTC):** 2026-04-22
- **Owner:** QA + Platform + Backend + Frontend
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Matrix (deduplicated canonical table)

| Scenario | Status | Test evidence | Workflow evidence | Script evidence | Doc evidence |
|---|---|---|---|---|---|
| Owner bootstrap | `done` | — | `.github/workflows/ci.yml` | `scripts/bootstrap_tenant.py` | `backend/app/services/tenants/bootstrap/service.py` |
| Demo bootstrap | `done` | — | `.github/workflows/ci.yml` | `scripts/bootstrap_demo_tenant.py` | `backend/app/services/demo_bootstrap.py` |
| Dev admin bootstrap | `done` | — | `.github/workflows/ci.yml` | — | `backend/app/services/dev_bootstrap.py` |
| Template catalog card creation | `done` | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `/api/v1/templates/catalog` |
| Template version upload | `done` | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `/api/v1/templates/{id}/versions:upload` |
| Template lint + preview API | `done` | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `/api/v1/templates/{id}/versions/{version_id}:lint`, `/api/v1/templates/{id}/versions/{version_id}:preview` |
| Organization document generation | `done` | `tests/test_documents_generate.py` | `.github/workflows/ci.yml` | — | `/api/v1/documents/generate` |
| Branch/site template scope | `partial` | `tests/test_template_catalog_scope.py` | `.github/workflows/ci.yml` | — | `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Header/footer apply | `done` | `tests/api/test_branding_api.py` | `.github/workflows/ci.yml` | — | branding modules |
| Replace dry-run/reporting | `partial` | replace API/tests (foundation only) | `.github/workflows/ci.yml` | — | replace API docs |
| PDF conversion | `partial` | existing celery/pdf tests | `.github/workflows/ci.yml` | — | celery/pdf modules |
| Approval/sign/archive handoff | `partial` | approval/sign/document preview tests (partial) | `.github/workflows/ci.yml` | — | flow docs |
| Tenant isolation | `done` | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_abac_query_isolation.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py` | `docs/TESTING.md` |
| Structured errors contract | `done` | `tests/test_errors.py`, `tests/e2e/final_regression/test_final_regression_api.py`, frontend vitest slices | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `docs/TESTING.md` |
| Notifications contract hardening | `done` | `tests/api/test_notifications_calendar_api.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/api/test_notifications_calendar_api.py` | `GAP_REPORT.md` |
| OpenAPI contract stability | `done` | `tests/contract/test_openapi_contract.py` | `.github/workflows/ci.yml` | `PYTHONPATH=backend python scripts/contract/validate.py` | `docs/TESTING.md` |
| Idempotent generation/writes | `done` | `tests/test_idempotency.py`, integration idempotency tests | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `docs/TESTING.md` |
| Async status transparency | `done` | `tests/integration/test_job_status_flow.py`, outbox/webhooks tests | `.github/workflows/ci.yml` | `./scripts/pytest.sh ...` | `docs/TESTING.md` |
| Search/export performance smoke | `partial` | — | `.github/workflows/ci.yml` | `python scripts/perf/api_load.py --help` | `scripts/perf/README.md` |
| Release docs completeness | `done` | `tests/e2e/test_release_candidate_docs.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py` | release docs |
| Repository audit reproducibility | `done` | `tests/test_repo_audit.py` | `.github/workflows/ci.yml` | `python scripts/repo_audit.py` | repo audit docs |
| Frontend production bundle stability | `done` | — | `.github/workflows/ci.yml` | `npm --prefix frontend run build` | `frontend/vite.config.ts` |
| Frontend no-dead-end wizard actions | `done` | frontend vitest wizard suites | `.github/workflows/e2e-smoke.yml` | `cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage` | frontend wizard docs |
| Frontend branded preview continuity | `done` | `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `.github/workflows/ci.yml` | `cd frontend && npx vitest run src/__tests__/DocumentsWizardPage.test.tsx` | `frontend/src/stores/documentsWizard.ts` |
| TZ Wave 3 document signed hook | `done` | `tests/services/test_domain_hooks_document_signed.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/services/test_domain_hooks_document_signed.py` | TZ wave docs |
| TZ Wave 5 EDO adapter factory | `done` | `tests/services/test_edo_integration_factory.py` | `.github/workflows/ci.yml` | `./scripts/pytest.sh tests/services/test_edo_integration_factory.py` | TZ wave docs |
| TZ Wave 4 workspace hub routes | `partial` | frontend route tests (partial) | `.github/workflows/e2e-smoke.yml` | `npm --prefix frontend run build` | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx` |

## CI / merge-gate mapping

- Canonical testing map: `docs/TESTING.md`.
- Coverage non-regression gate: `docs/stabilization/coverage.md` + `.github/workflows/ci.yml` (`backend-tests`).
- Typical acceptance bundle:

```bash
make final-acceptance
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
python scripts/perf/api_load.py --help
python scripts/pilot_readiness.py
```

## Linked decision docs

- Gap analysis: `GAP_REPORT.md`
- Release verdict: `RELEASE_READINESS.md`
- Accepted constraints: `KNOWN_LIMITATIONS.md`
- Stabilization plan: `docs/stabilization/PLAN.md`
