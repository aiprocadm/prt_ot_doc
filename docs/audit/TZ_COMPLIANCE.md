# TZ Compliance Matrix (A–J)

Legend: **OK** / **Partial** / **Missing**; severity: **P0** (must-fix), **P1**, **P2**.

| Requirement | Implementation (files/modules/endpoints) | Status | Severity | Plan/Fix |
|---|---|---:|---:|---|
| A) Единое Core + модульные вертикали | Backend routers/domains (`backend/app/api`, `backend/app/domains`), frontend module pages (`frontend/src/pages`) | OK | - | - |
| B) Multi-tenant: `/v1` business routes require `X-Tenant` | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `tests/test_tenant_header_required.py` | OK | - | - |
| B) Frontend tenant-context enforcement | `frontend/src/api/client.ts`, `frontend/src/components/tenant/TenantGate.tsx`, tests in `frontend/src/__tests__` | OK | - | - |
| C) RBAC + ABAC (company/site/document/status/risk_level) | `backend/app/core/security.py`, ABAC tests in `tests/unit/test_abac_policies.py` | Partial | P1 | Expand ABAC checks for all mutation paths and all listed attributes. |
| D) Audit append-only + immutable | `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`, `tests/test_audit_log_immutability.py` | OK | - | - |
| E) Core entities (контрагент/договор/заказ/счет/акт/оргструктура/сотрудник) | APIs and models under `backend/app/api/routes/*`, `backend/app/models/*` | Partial | P1 | Continue normalization and tighter lifecycle coverage where only CRUD skeleton exists. |
| F) Template strict versioning + delete guard 409 | `backend/app/api/routes/documents.py`, `tests/test_documents_generate.py`, `tests/test_template_delete.py` | OK | - | - |
| F) DOCX→PDF + watermark/QR/stamps | `backend/app/services/docx.py`, `backend/app/services/pdf.py`, pipeline tests | Partial | P2 | Keep MVP output; advanced stamping/QR can be expanded later. |
| G) Idempotency-Key for critical operations | `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`, documents tests | OK | - | - |
| G) Outbox: tx write + dispatcher + retries/backoff + dead-letter + metrics | `backend/app/services/outbox.py`, `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py` | OK | - | - |
| G) Webhooks routing: global + per-tenant overrides | `backend/app/services/webhooks.py`, webhook tests `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | OK | - | - |
| H) Domain contours (Risks/PPE/Training/Medical/Incidents/Inspections) | domain routes in `backend/app/api/routes/`, API/integration tests under `tests/api`/`tests/integration` | Partial | P1 | Keep expanding parity for validation/state-machine coverage. |
| I) Unified obligations/tasks + reminders/overdue | `backend/app/services/obligations.py`, `backend/app/services/tasks.py`, obligations APIs/tests | OK | - | - |
| J) Codespaces runability + dockerless + test discovery | `.devcontainer/*`, Make/scripts, `.vscode/settings.json`, docs runbook/README | OK | - | Updated quick-start install commands to include both runtime and dev dependencies. |

## Summary (current cycle)
- **OK:** 10
- **Partial:** 4
- **Missing:** 0
- **P0:** 0 open
- **P1:** 3 open
- **P2:** 1 open

## Security & Tenant Isolation Risks
- **P1:** ABAC attribute coverage is strong but not yet uniformly enforced across every low-frequency mutation route.
- Tenant mismatch and missing tenant header protections are covered and tested.

## Runability Risks (Codespaces)
- Primary risk was incomplete dependency install if only dev requirements are installed in ad-hoc setup.
- **Fix applied:** docs now require `pip install -r requirements.txt -r requirements-dev.txt` in quick-start/runbook.

## Test Discovery Risks
- `pytest --collect-only -q` is green after installing full dependency set.
- VS Code panel integration remains configured via `.vscode/settings.json` + `vscode_pytest.py`.
