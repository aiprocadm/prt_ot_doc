# TZ Compliance Matrix (A–J)

Legend: **OK** / **Partial** / **Missing**; severity: **P0** (must-fix), **P1**, **P2**.

| Requirement | Implementation (files/modules/endpoints) | Status | Severity | Fix plan |
|---|---|---:|---:|---|
| A) Core + vertical modular architecture | `backend/app/api/*`, `backend/app/domains/*`, `frontend/src/pages/*`, `docs/architecture/*` | OK | - | - |
| B) Multi-tenant required on business `/v1` routes | `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, test `tests/test_tenant_header_required.py` | OK | - | - |
| B) Frontend always injects `X-Tenant` and blocks calls without tenant context | `frontend/src/api/client.ts`, tests `frontend/src/__tests__/apiClient.test.ts`, `frontend/src/__tests__/TenantGate.test.tsx` | OK | - | - |
| C) RBAC+ABAC and domain constraints | `backend/app/core/security.py`, tests `tests/unit/test_abac_policies.py`, `tests/test_rbac_abac.py` | Partial | P1 | Expand object-level ABAC checks across all update flows (`status`, `risk_level`, `site_id`, `document_id`). |
| D) Append-only audit log + immutable API | `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`, `tests/test_audit_log_immutability.py` | OK | - | - |
| E) Core entities (counterparty/contracts/orders/invoices/org structure/workplace/person) | APIs in `backend/app/api/routes/*`, models in `backend/app/models/*` | Partial | P1 | Continue strengthening cross-entity linkage in ERP workflows. |
| F) Template strict versioning (`template_code`,`version`) + delete guard 409 | Document/template routes + tests `tests/test_documents_generate.py`, `tests/test_template_delete.py` | OK | - | - |
| F) DOCX→PDF pipeline + stamps/watermark/QR | `backend/app/services/docx.py`, `pdf.py`, `pipeline.py` | Partial | P2 | Keep MVP pipeline; add production-grade stamping/QR renderer later. |
| G) Idempotency-Key for critical operations | `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`, document/risk tests | OK | - | - |
| G) Outbox pattern with retries/backoff/dead-letter/metrics | `backend/app/services/outbox.py`, tests `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py` | OK | - | - |
| G) Required webhooks + routing (global + tenant override) | `backend/app/services/webhooks.py`, `WebhookSubscription` model, tests `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | OK | - | - |
| H) Risk module deterministic results + action plan | `backend/app/domains/risk/*`, `backend/app/api/routes/risk.py`, tests `tests/test_risk_assessment_kpi5.py`, `tests/test_risk_engine.py` | OK | - | - |
| H) PPE / Training / Medical / Incidents / Inspections MVP contour | domain routes/services/tests under `backend/app/api/routes/` and `tests/api/` | Partial | P1 | Align state machines and ABAC parity across modules. |
| I) Unified obligations/tasks + reminders + overdue reporting | `backend/app/services/obligations.py`, `tasks.py`, `backend/app/api/routes/obligations.py`, tests `tests/integration/test_obligation_tasks.py` | OK | - | - |
| J) Codespaces runability + dockerless mode + test discovery | `.devcontainer/*`, scripts in `scripts/`, `.vscode/settings.json`, `pyproject.toml` pytest config | OK | - | - |

## Summary counts
- **OK:** 10
- **Partial:** 4
- **Missing:** 0
- **P0 gaps:** 0
- **P1 gaps:** 3
- **P2 gaps:** 1

## P0 fixes implemented in this cycle
- No new functional P0 gaps were detected during re-audit; mandatory KPI paths remained green.
- `pytest` discovery stability was hardened by setting explicit `asyncio_default_fixture_loop_scope = "function"` in `pyproject.toml` to remove runtime ambiguity in Codespaces test discovery.

## Security & Tenant Isolation Risks
- Residual **P1** risk: ABAC coverage breadth is not yet uniform on every less-used object mutation path.
- Tenant header/token mismatch remains hard-failed (`403`) and business `/v1` routes still reject missing `X-Tenant` (`400`).

## Runability Risks (Codespaces)
- Dockerless workflow is stable (`make dev:lite`, `make test:lite`).
- Frontend tests emit non-blocking warnings (React Router future flags / `act(...)`) but complete successfully.

## Test Discovery Risks
- Backend discovery is green (`pytest --collect-only -q`) after explicit async fixture loop scope pin.
- VS Code testing panel remains aligned with `.vscode/settings.json` runner configuration.
