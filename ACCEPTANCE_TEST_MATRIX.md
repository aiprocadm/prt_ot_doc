# ACCEPTANCE_TEST_MATRIX

| Scenario | Evidence | Status |
|---|---|---|
| Owner bootstrap | `scripts/bootstrap_tenant.py`, `backend/app/services/tenants/bootstrap/service.py` | Implemented |
| Demo bootstrap | `scripts/bootstrap_demo_tenant.py`, `backend/app/services/demo_bootstrap.py` | Implemented |
| Dev admin bootstrap | `backend/app/services/dev_bootstrap.py` | Implemented |
| Custom template card creation | `/api/v1/templates/catalog`, `tests/test_template_catalog_scope.py` | Hardened |
| Custom template version upload | `/api/v1/templates/{id}/versions:upload`, `tests/test_template_catalog_scope.py` | Hardened |
| Template lint | `/api/v1/templates/{id}/versions/{version_id}:lint` | Implemented |
| Template preview | `/api/v1/templates/{id}/versions/{version_id}:preview` | Implemented |
| Org/company document generation | `/api/v1/documents/generate`, `tests/test_documents_generate.py` | Implemented |
| Branch/site-specific template scope | metadata-backed scope contract, `/templates` UI, `tests/test_template_catalog_scope.py` | Foundation+hardened |
| Header/footer apply | branding + headers modules, `tests/api/test_branding_api.py` | Implemented |
| Replace dry-run/reporting | replace API/tests | Implemented foundation |
| PDF conversion | celery/pdf modules and tests | Implemented foundation |
| Approval / sign / archive handoff | approval/sign/document preview flows | Partial but real |
| Tenant isolation | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_abac_query_isolation.py` | `./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py` |
| Structured errors contract | `tests/test_errors.py`, `tests/e2e/final_regression/test_final_regression_api.py`, `frontend/src/__tests__/apiClient.test.ts`, `frontend/src/__tests__/commonStates.test.tsx` | `./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py && cd frontend && npx vitest run apiClient commonStates` |
| Notifications contract hardening | `tests/api/test_notifications_calendar_api.py` | `./scripts/pytest.sh tests/api/test_notifications_calendar_api.py` |
| OpenAPI / contract stability | `tests/contract/test_openapi_contract.py`, `scripts/contract/validate.py` | `./scripts/pytest.sh tests/contract/test_openapi_contract.py && PYTHONPATH=backend python scripts/contract/validate.py` |
| Idempotent generation / writes | `tests/test_idempotency.py`, `tests/integration/test_idempotency_generate.py`, `tests/integration/test_pipeline_idempotency.py` | `./scripts/pytest.sh tests/test_idempotency.py tests/integration/test_idempotency_generate.py tests/integration/test_pipeline_idempotency.py` |
| Async status transparency | `tests/integration/test_job_status_flow.py`, `tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py` | `./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/test_outbox_dispatch.py tests/test_webhooks_dispatch.py` |
| Search / export performance smoke foundation | `scripts/perf/api_load.py`, `scripts/perf/README.md` | `python scripts/perf/api_load.py --help` |
| Release docs completeness | `tests/e2e/test_release_candidate_docs.py` | `./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py` |
| Repository audit reproducibility | `scripts/repo_audit.py`, `tests/test_repo_audit.py` | `python scripts/repo_audit.py && pytest -q tests/test_repo_audit.py` |
| Frontend production bundle stability | `frontend/vite.config.ts`, `npm --prefix frontend run build` | `npm --prefix frontend run build` |
| Frontend no-dead-end wizard actions | `frontend/src/__tests__/GeneratePackWizardPage.test.tsx`, `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage` |
| Frontend branded preview state continuity | `frontend/src/stores/documentsWizard.ts`, `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `cd frontend && npx vitest run src/__tests__/DocumentsWizardPage.test.tsx` |
| TZ Wave 3 — document signed → follow-up task | `backend/app/services/domain_hooks.py`, `tests/services/test_domain_hooks_document_signed.py` | `./scripts/pytest.sh tests/services/test_domain_hooks_document_signed.py` |
| TZ Wave 5 — EDO adapter factory (stub vs HTTP) | `backend/app/services/integrations/factory.py`, `tests/services/test_edo_integration_factory.py` | `./scripts/pytest.sh tests/services/test_edo_integration_factory.py` |
| TZ Wave 4 — workspace hub routes render | `frontend/src/pages/workspace/WorkspaceAttentionPage.tsx`, `WorkspaceDataQualityPage.tsx`, `SyncConflictHelpPage.tsx` | `npm --prefix frontend run build` |


## CI / merge-gate mapping

Связка с каноническим гайдом: `docs/TESTING.md`.

- **Что запускается локально (pre-PR / RC):** `make final-acceptance` и целевые команды из сценариев этой матрицы.
- **Что запускается в CI автоматически:**
  - backend/integration slices → `backend-tests`,
  - контрактные проверки → `openapi-contract`,
  - frontend flows/quality → `frontend-tests`,
  - compose smoke → `smoke-compose`,
  - perf smoke → `perf-smoke`.
- **Что блокирует merge:** любой fail в перечисленных CI jobs, а также security gates из CI workflow.

Связанные документы:
- `docs/stabilization/coverage.md` — coverage baseline и non-regression gate в `backend-tests`;
- `docs/TESTING.md` — общая тестовая пирамида и обязательные pre-PR/RC проверки.

## 3. Acceptance bundle commands

```bash
make final-acceptance
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
python scripts/perf/api_load.py --help
python scripts/pilot_readiness.py
```

## 4. Related evidence

- Coverage source of truth: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Workflow/event reference: `docs/WORKFLOWS_AND_EVENTS.md`
- Observability reference: `docs/OBSERVABILITY.md`
- Gap analysis: `GAP_REPORT.md`
- Release decision log: `RELEASE_READINESS.md`
- Residual risks / accepted limitations: `KNOWN_LIMITATIONS.md`

### 2026-03-21 notifications hardening evidence
- `tests/api/test_notifications_calendar_api.py` validates unread filters plus predictable structured 422 behavior for invalid enum, cursor, and calendar-source inputs.
- `tests/test_workflow_api.py` remains the cross-module regression slice for workflow + notifications + NPA foundations.
| Scenario | Status | Canonical code/docs |
|---|---|---|
| Owner bootstrap | implemented | `scripts/bootstrap_tenant.py`, `docs/OWNER_ADMIN_ACCESS.md` |
| Demo bootstrap | implemented | `scripts/bootstrap_demo_tenant.py`, `docs/DEMO_ACCESS.md` |
| Custom template catalog card | implemented | `backend/app/api/v1/router.py`, `frontend/src/features/templates/TemplateFormDialog.tsx` |
| Template version upload + lint + preview | implemented foundation | `backend/app/api/v1/router.py`, `frontend/src/features/templates/TemplateDetails.tsx` |
| Org/branch-scoped template metadata | implemented foundation | `backend/app/api/v1/router.py`, `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Org-specific document generation | implemented foundation | `backend/app/api/routes/documents.py` |
| Template contract coherence (backend + frontend) | hardened | `backend/app/modules/templates/schemas.py`, `backend/app/api/v1/router.py`, `frontend/src/types/dto/templates.ts`, `frontend/src/types/forms/templates.ts` |
