# ACCEPTANCE TEST MATRIX

Финальная матрица приемки release candidate. Документ фиксирует, каким именно автотестом или smoke/probe-командой подтверждается каждый критичный сценарий из RC-wave.

## 1. Critical end-to-end scenarios

| Scenario | Backend/API coverage | Frontend / UX / smoke coverage | Acceptance evidence | Status |
|---|---|---|---|---|
| Tenant bootstrap / onboarding | `tests/e2e/pilot_smoke/test_pilot_smoke_matrix.py`, `tests/test_tenant_header_required.py`, `tests/test_tenancy_enforcement.py` | `docs/TENANT_BOOTSTRAP_RUNBOOK.md`, `docs/FIRST_RUN_ONBOARDING.md` | `python scripts/pilot_readiness.py` | Ready for pilot |
| Employees import / кадровый контур | `tests/api/test_person_crud.py`, `tests/api/test_company_crud.py` | registry UX covered by persons/companies pages and route smoke | `./scripts/pytest.sh tests/api/test_person_crud.py tests/api/test_company_crud.py` | Stable CRUD baseline |
| Document/package generation | `tests/test_documents_generate.py`, `tests/test_package_pipeline.py`, `tests/integration/test_pipeline_steps_happy_path.py` | document wizard/pages backed by existing frontend smoke suites | `make final-acceptance` → sample render/pdf/export flow | Stable |
| Approval flow | `tests/api/test_edo_signature_approval_mvp.py`, `tests/services/test_document_workflow.py` | timeline/status widgets in critical pages | backend acceptance + runbook walkthrough | Stable MVP |
| Signature journal / sign status | `tests/api/test_edo_signature_approval_mvp.py`, `tests/test_outbox_service.py` | sign/approval detail UX via shared status/timeline components | backend acceptance + `docs/runbook/DEMO_WALKTHROUGH_3_EDO_SIGNATURE_APPROVAL.md` | Stable MVP |
| Send to client portal | `tests/test_client_portal_api.py`, `tests/test_pack_download_api.py` | portal packages/history/request screens smoke-covered by existing route tests | API evidence + portal runbook | Stable MVP |
| PPE issuance | `tests/api/test_ppe_api.py`, `tests/api/test_ppe_events.py` | PPE registries/pages in existing frontend shell | backend acceptance | Stable |
| Training assignment / completion | `tests/api/test_training_api.py`, `tests/api/test_training_enterprise_api.py`, `tests/test_training_enrollment_service.py` | learner/training pages covered by app/router smoke baseline | backend acceptance | Stable |
| Incident registration | `tests/api/test_incidents_api.py` | incident page shell in routed frontend app | backend acceptance | Stable MVP |
| Inspection / checklist / findings | `tests/api/test_inspections_api.py`, `tests/integration/test_prescriptions_api.py` | inspection page shell in routed frontend app | backend acceptance | Stable MVP |
| Prescription / corrective action closure | `tests/integration/test_prescriptions_api.py`, `tests/integration/test_obligation_tasks.py` | workflow/task UX via shared task screens | backend acceptance | Stable MVP |
| CRM -> contract/order -> invoice/act | `tests/integration/test_finance_entities.py`, `tests/test_billing_events_api.py` | finance/admin screens covered by route-level smoke and documented flows | targeted backend integration checks | Stable foundation |
| Billing limit enforcement | `tests/test_billing_service.py`, `tests/test_tenant_billing_services.py`, `tests/test_document_limits.py` | billing/usage pages documented and route-exposed | backend acceptance | Stable |
| Export / report job | `tests/api/test_exports_foundation_api.py`, `tests/api/test_reports_api.py`, `tests/integration/test_job_status_flow.py` | export/report screens route through async jobs | `make final-acceptance` + perf notes | Stable |
| Workflow task completion / delegation / escalation | `tests/test_workflow_api.py`, `tests/unit/test_task_reminders.py` | workflow inbox/detail pages reuse task cards/timeline widgets | backend acceptance | Stable MVP |

### RC wave additions validated in this change set

- Pack generation wizard retry path now re-requests presets inside the screen instead of forcing `window.location.reload()`. Evidence: `frontend/src/__tests__/GeneratePackWizardPage.test.tsx`.
- Document wizard archive step no longer ends with a disabled MVP placeholder button: it shows archive readiness status and real navigation to archive/approvals. Evidence: `frontend/src/__tests__/DocumentsWizardPage.test.tsx`.

## 2. Cross-cutting release criteria

| Criterion | Primary tests / checks | Command |
|---|---|---|
| Tenant isolation | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_abac_query_isolation.py` | `./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py` |
| Structured errors contract | `tests/test_errors.py`, `tests/e2e/final_regression/test_final_regression_api.py`, `frontend/src/__tests__/apiClient.test.ts`, `frontend/src/__tests__/commonStates.test.tsx` | `./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py && cd frontend && npx vitest run apiClient commonStates` |
| OpenAPI / contract stability | `tests/contract/test_openapi_contract.py`, `scripts/contract/validate.py` | `./scripts/pytest.sh tests/contract/test_openapi_contract.py && PYTHONPATH=backend python scripts/contract/validate.py` |
| Idempotent generation / writes | `tests/test_idempotency.py`, `tests/integration/test_idempotency_generate.py`, `tests/integration/test_pipeline_idempotency.py` | `./scripts/pytest.sh tests/test_idempotency.py tests/integration/test_idempotency_generate.py tests/integration/test_pipeline_idempotency.py` |
| Async status transparency | `tests/integration/test_job_status_flow.py`, `tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py` | `./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/test_outbox_dispatch.py tests/test_webhooks_dispatch.py` |
| Search / export performance smoke foundation | `scripts/perf/api_load.py`, `scripts/perf/README.md` | `python scripts/perf/api_load.py --help` |
| Release docs completeness | `tests/e2e/test_release_candidate_docs.py` | `./scripts/pytest.sh tests/e2e/test_release_candidate_docs.py` |
| Repository audit reproducibility | `scripts/repo_audit.py`, `tests/test_repo_audit.py` | `pytest -q tests/test_repo_audit.py && python scripts/repo_audit.py` |
| Repository audit reproducibility | `scripts/repo_audit.py`, `tests/test_repo_audit.py` | `python scripts/repo_audit.py && pytest -q tests/test_repo_audit.py` |
| Frontend production bundle stability | `frontend/vite.config.ts`, `npm --prefix frontend run build` | `npm --prefix frontend run build` |
| Frontend no-dead-end wizard actions | `frontend/src/__tests__/GeneratePackWizardPage.test.tsx`, `frontend/src/__tests__/DocumentsWizardPage.test.tsx` | `cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage` |

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
