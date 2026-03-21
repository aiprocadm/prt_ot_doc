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
