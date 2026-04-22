# ACCEPTANCE_TEST_MATRIX

- **Updated on:** 2026-04-22
- **Owner:** QA + Platform + Backend + Frontend
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Matrix

| Scenario | Status | Executable evidence (path/command) |
|---|---|---|
| Owner bootstrap | done | `scripts/bootstrap_tenant.py`, `backend/app/services/tenants/bootstrap/service.py` |
| Demo bootstrap | done | `scripts/bootstrap_demo_tenant.py`, `backend/app/services/demo_bootstrap.py` |
| Dev admin bootstrap | done | `backend/app/services/dev_bootstrap.py` |
| Template catalog card creation | done | `/api/v1/templates/catalog`, `tests/test_template_catalog_scope.py` |
| Template version upload | done | `/api/v1/templates/{id}/versions:upload`, `tests/test_template_catalog_scope.py` |
| Template lint + preview API | done | `/api/v1/templates/{id}/versions/{version_id}:lint`, `/api/v1/templates/{id}/versions/{version_id}:preview` |
| Organization document generation | done | `/api/v1/documents/generate`, `tests/test_documents_generate.py` |
| Branch/site template scope | partial | `tests/test_template_catalog_scope.py`, `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Header/footer apply | done | `tests/api/test_branding_api.py`, branding modules |
| Replace dry-run/reporting | partial | replace API/tests (foundation only) |
| PDF conversion | partial | celery/pdf modules + existing tests |
| Approval/sign/archive handoff | partial | approval/sign/document preview flows |
| Tenant isolation | done | `./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py` |
| Structured errors contract | done | `./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py && cd frontend && npx vitest run apiClient commonStates` |
| Notifications contract hardening | done | `./scripts/pytest.sh tests/api/test_notifications_calendar_api.py` |
| OpenAPI contract stability | done | `./scripts/pytest.sh tests/contract/test_openapi_contract.py && PYTHONPATH=backend python scripts/contract/validate.py` |
| Idempotent generation/writes | done | `./scripts/pytest.sh tests/test_idempotency.py tests/integration/test_idempotency_generate.py tests/integration/test_pipeline_idempotency.py` |
| Async status transparency | done | `./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/test_outbox_dispatch.py tests/test_webhooks_dispatch.py` |
| Search/export performance smoke | partial | `python scripts/perf/api_load.py --help`, `scripts/perf/README.md` |
| Release docs completeness | done | `./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py` |
| Repository audit reproducibility | done | `python scripts/repo_audit.py && pytest -q tests/test_repo_audit.py` |
| Frontend production bundle stability | done | `npm --prefix frontend run build`, `frontend/vite.config.ts` |
| Frontend no-dead-end wizard actions | done | `cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage` |
| Frontend branded preview continuity | done | `frontend/src/stores/documentsWizard.ts`, `cd frontend && npx vitest run src/__tests__/DocumentsWizardPage.test.tsx` |
| TZ Wave 3 document signed hook | done | `./scripts/pytest.sh tests/services/test_domain_hooks_document_signed.py` |
| TZ Wave 5 EDO adapter factory | done | `./scripts/pytest.sh tests/services/test_edo_integration_factory.py` |
| TZ Wave 4 workspace hub routes | partial | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx`, `npm --prefix frontend run build` |

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
