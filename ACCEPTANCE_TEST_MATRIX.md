# ACCEPTANCE_TEST_MATRIX

## Scope
Release-candidate acceptance coverage for the final stabilization wave. The matrix below maps critical business scenarios to executable checks already present in the repository and highlights the main evidence path for pilot/demo acceptance.

| Scenario | Backend / integration evidence | Frontend / e2e evidence | Status | Notes |
|---|---|---|---|---|
| Tenant bootstrap / isolation | `tests/test_tenancy_enforcement.py`, `tests/integration/test_tenant_isolation.py`, `tests/e2e/pilot_smoke/test_pilot_smoke_matrix.py` | route smoke via existing frontend suite | Ready | `X-Tenant` remains mandatory and regression-covered. |
| Employee import / кадровый контур | `tests/api/test_person_crud.py`, `tests/api/test_company_crud.py` | `frontend` persons smoke | Ready with manual import drill | CRUD path is covered; bulk import remains validated via pilot smoke/data seeding. |
| Document/package generation | `tests/test_documents_generate.py`, `tests/test_package_pipeline.py`, `tests/services/test_pack_generation_pipeline.py` | documents/package pages in frontend smoke | Ready | Includes idempotent generation and package pipeline checks. |
| Approval -> sign -> EDO | `tests/api/test_edo_signature_approval_mvp.py` | manual UI validation supported, API flow automated | Ready | Mock provider path is acceptance baseline for pilot. |
| Client portal dispatch | `tests/test_client_portal_api.py` | `ClientPortalPackagesPage.test.tsx`, `ClientPortalHistoryAndRequests.test.tsx` | Ready | Portal package status/history paths are stable. |
| PPE issuance | `tests/api/test_ppe_api.py`, `tests/api/test_ppe_events.py` | PPE registry page smoke | Ready | Journal/events covered. |
| Training assignment / completion | `tests/api/test_training_api.py`, `tests/api/test_training_enterprise_api.py` | training page tests | Ready | Overdue/enterprise flows covered by API regression. |
| Incident registration | `tests/api/test_incidents_api.py` | incident page smoke/manual | Ready | Corrective-action path continued below. |
| Inspection -> prescription -> closure | `tests/api/test_inspections_api.py`, `tests/integration/test_prescriptions_api.py` | inspection/prescription UI smoke/manual | Ready | Core checklist/finding/closure flow automated on API side. |
| CRM -> contract/order -> invoice/act | `tests/integration/test_finance_entities.py` | billing/admin UI smoke/manual | Partial-ready | API foundation is present; end-to-end UI contract remains pilot checklist item. |
| Billing limit enforcement | `tests/test_billing_service.py`, `tests/test_tenant_billing_services.py`, `tests/test_billing_events_api.py` | billing screens manual/UI smoke | Ready | Hard limit behavior remains contract-tested. |
| Export/report job | `tests/api/test_exports_foundation_api.py`, `tests/integration/test_job_status_flow.py`, `tests/api/test_reports_api.py` | exports page tests/manual | Ready | Job tracking and download-link lifecycle are automated. |
| Workflow completion / delegation / escalation | `tests/test_workflow_api.py`, `tests/unit/test_task_reminders.py` | workflow page smoke/manual | Ready | Delegation and SLA paths are regression-covered. |
| Structured errors / API contract | `tests/test_errors.py`, `tests/contract/test_openapi_contract.py`, `tests/e2e/final_regression/test_final_regression_api.py` | n/a | Ready | Error envelope fields are now enforced consistently. |

## Recommended RC verification commands
```bash
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_job_status_flow.py
./scripts/pytest.sh tests/api/test_edo_signature_approval_mvp.py tests/test_client_portal_api.py
./scripts/pytest.sh tests/api/test_ppe_api.py tests/api/test_training_enterprise_api.py
./scripts/pytest.sh tests/api/test_incidents_api.py tests/api/test_inspections_api.py tests/integration/test_prescriptions_api.py
./scripts/pytest.sh tests/test_workflow_api.py tests/test_billing_service.py tests/api/test_exports_foundation_api.py
npm --prefix frontend run test
```
