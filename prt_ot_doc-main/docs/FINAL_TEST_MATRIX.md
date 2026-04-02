# FINAL TEST MATRIX

## Final regression suite location
- `tests/e2e/final_regression/test_final_regression_api.py`

## Tenant / auth
- login + protected routes: existing `tests/test_auth_login.py`, `tests/test_api_guardrails.py`
- business route without X-Tenant => 400: `tests/e2e/final_regression/test_final_regression_api.py::test_business_route_requires_tenant_header`
- role-restricted denied: `tests/test_rbac_abac.py`, `tests/integration/test_admin_user_roles.py`
- ABAC foreign entity blocked: `tests/integration/test_abac_query_isolation.py`, `tests/integration/test_tenant_isolation.py`

## Documents pipeline
- template upload/select/delete guards: `tests/test_templates_pipeline_api.py`, `tests/test_template_delete.py`
- package generation/idempotency: `tests/test_documents_generate.py`, `tests/integration/test_pipeline_idempotency.py`, `tests/e2e/final_regression/*`
- headers/replace/pdf/archive flow: `tests/test_package_pipeline.py`, `tests/test_replace_api.py`, `tests/test_services_pdf_unit.py`

## EDO / approvals / sign
- core API flow: `tests/api/test_edo_signature_approval_mvp.py`
- webhook dispatch/routing: `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py`

## Risk / PPE / training / inspections
- risk: `tests/test_risk_engine.py`, `tests/test_risk_assessment_kpi5.py`
- PPE: `tests/api/test_ppe_api.py`, `tests/api/test_ppe_events.py`
- training: `tests/api/test_training_api.py`, `tests/domains/test_training_domain.py`
- inspections/incidents: `tests/api/test_inspections_api.py`, `tests/api/test_incidents_api.py`

## Search / exports / reports
- search indexing/extractors: `tests/test_search_indexing_next45.py`, `tests/test_search_extractors_next35.py`
- exports/report API: `tests/api/test_reports_api.py`, `tests/test_next62_analytics_search_export_center.py`

## Client portal
- API data boundary: `tests/test_client_portal_api.py`

## Billing / quotas / ops
- billing/quota: `tests/test_billing_service.py`, `tests/test_tenant_billing_services.py`, `tests/test_document_limits.py`
- health/readiness: `tests/test_health_ready.py`, `tests/test_smoke_observability.py`

## Security / reliability
- upload security: `tests/test_files_upload.py`, `tests/test_files_core_next54.py`
- audit immutability: `tests/test_audit_log_immutability.py`
- idempotency/outbox: `tests/test_idempotency.py`, `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py`

## Final acceptance runner coverage
`make final-acceptance` executes critical subset:
1. backend critical tests
2. frontend critical checks (best-effort)
3. e2e final regression subset
4. openapi drift checks
5. migrations heads
6. health/readiness
7. sample render/pdf/export tests
8. schema consistency verification

Artifacts:
- `artifacts/final_acceptance/summary.json`
- `artifacts/final_acceptance/summary.md`
- `artifacts/final_acceptance/*.log`
