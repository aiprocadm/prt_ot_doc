# TZ Compliance Matrix (A–J)

Legend: **OK** / **Partial** / **Missing**; severity: **P0** (must-fix), **P1**, **P2**.

| Requirement | Implementation (files/modules/endpoints) | Status | Severity | Fix plan |
|---|---|---:|---:|---|
| A) Core + vertical modular architecture | `backend/app/api/*`, `backend/app/domains/*`, `frontend/src/pages/*`, docs in `docs/architecture/*` | OK | - | - |
| B) Multi-tenant required on business `/v1` routes | `TenantMiddleware` + `tenant_required`: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`; tests `tests/test_tenant_header_required.py` | OK | - | - |
| B) Frontend always injects `X-Tenant` and blocks calls without tenant context | `frontend/src/api/client.ts`; tests `frontend/src/__tests__/apiClient.test.ts`, `frontend/src/__tests__/TenantGate.test.tsx` | OK | - | - |
| C) RBAC+ABAC and domain constraints | `backend/app/core/security.py`, ABAC tests `tests/unit/test_abac_policies.py`, RBAC tests `tests/test_rbac_abac.py` | Partial | P1 | Expand ABAC attributes enforcement uniformly to all domain endpoints (`status`, `risk_level`, object-level policies). |
| D) Append-only audit log + immutable API | `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`, tests `tests/test_audit_log_immutability.py` | OK | - | - |
| E) Core entities (company/org/person/contracts/invoices/tasks/events) | routes/models across `backend/app/api/routes/*`, `backend/app/models/models.py`, `backend/app/models/finance.py`, obligations stack | Partial | P1 | Continue normalizing cross-domain links for full ERP-level workflows. |
| F) Template version strictness + delete guard 409 | template/document routes + tests `tests/test_template_delete.py`, `tests/test_documents_generate.py` | OK | - | - |
| F) DOCX→PDF + stamps/watermarks/QR | pipeline services: `backend/app/services/docx.py`, `backend/app/services/pdf.py`, `backend/app/services/pipeline.py` | Partial | P2 | Replace placeholders with production stamping/qr engine. |
| G) Idempotency for critical operations | middleware/service: `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`; docs/risk tests | OK | - | - |
| G) Outbox pattern with retries/backoff/DLQ/metrics | `backend/app/services/outbox.py`, tests `tests/test_outbox_dispatch.py`, `tests/test_outbox_service.py` | OK | - | - |
| G) Webhooks for required events + routing global/per-tenant override | `backend/app/services/webhooks.py`, outbox emission in domain routes/services, tests `tests/test_webhook_routing.py`, `tests/test_webhooks_dispatch.py` | OK | - | - |
| H) Risk module deterministic cards + action plan | risk domain/routes/models + KPI tests `tests/test_risk_assessment_kpi5.py`, `tests/test_risk_engine.py` | OK | - | - |
| H) PPE / Training / Incidents / Inspections scaffolds | dedicated APIs + tests under `tests/api/` and `tests/integration/` | Partial | P1 | Incrementally harden process states and ABAC parity across modules. |
| I) Unified obligations/tasks with reminders + overdue reports | `backend/app/services/obligations.py`, `backend/app/services/tasks.py`, routes and integration tests `tests/integration/test_obligation_tasks.py` | OK | - | - |
| J) Codespaces runability + dockerless + test discovery | `.devcontainer/*`, `scripts/dev_lite.sh`, `.vscode/settings.json`, `pytest --collect-only` | OK | - | - |

## P0 fixes implemented in this audit cycle
1. **RiskAssessed outbox payload normalization** aligned to typed event schema (`RiskAssessedPayload`) to avoid runtime 500 during risk assessment and keep KPI-5 path stable. Implemented in `backend/app/api/routes/risk.py`.
2. **Tenant isolation test expectation alignment** for token/header tenant mismatch (`403`) in risk KPI suite (`tests/test_risk_assessment_kpi5.py`).

## Security & Tenant Isolation Risks
- Main residual risk is policy breadth inconsistency across less-used endpoints (P1): ABAC attributes are implemented but not yet uniformly strict on every domain object update path.
- Header/token tenant mismatch is actively blocked with `403` in middleware (good hard fail).

## Runability Risks (Codespaces)
- `pytest_asyncio` deprecation warning (`asyncio_default_fixture_loop_scope` unset) is non-blocking but should be pinned in config to avoid future behavior drift.

## Test Discovery Risks
- Discovery is healthy (`pytest --collect-only` passes), but suite produces warning noise from deprecated libraries; keep under control to avoid masking real failures.
