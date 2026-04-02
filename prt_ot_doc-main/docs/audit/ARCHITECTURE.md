# Architecture Map (Discovery)

## 1) Repository structure
- `backend/` — FastAPI app factory + v1 API routers + domain services + SQLAlchemy models + Alembic migrations + Celery tasks/worker.
- `frontend/` — React/Vite SPA with tenant gate, role-aware route guards, and API client interceptors.
- `infra/`, `.devcontainer/`, `docker-compose.yml` — Docker/Codespaces bootstrap and local orchestration.
- `tests/` and `frontend/src/__tests__/` — backend pytest and frontend vitest suites.

## 2) Runtime entry points

### Backend
- ASGI entrypoint: `backend/app/main.py` (`app = create_app()`).
- App factory/lifecycle: `backend/app/api/app.py`.
- v1 route composition: `backend/app/api/v1/router.py`.
- Tenant middleware: `backend/app/middleware/tenant.py` + context/deps in `backend/app/core/tenant.py`.
- Settings: `backend/app/core/config.py`.

### Workers/outbox
- Celery worker bootstrap: `backend/app/worker.py`.
- Celery task modules: `backend/app/tasks.py`.
- Outbox + dispatch/retry/dead-letter/metrics: `backend/app/services/outbox.py`.
- Webhook delivery and routing: `backend/app/services/webhooks.py`.

### Frontend
- SPA bootstrap: `frontend/src/main.tsx`.
- Router tree: `frontend/src/router/AppRouter.tsx`.
- Tenant context gate/store: `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/stores/tenant.ts`.
- API client + `X-Tenant` injection/guard: `frontend/src/api/client.ts`.

## 3) Spec capability mapping locations
- Tenant enforcement: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, `tests/test_tenant_header_required.py`.
- RBAC/ABAC: `backend/app/core/security.py`, `tests/test_rbac_abac.py`, `tests/unit/test_abac_policies.py`.
- Audit append-only behavior: `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`, `tests/test_audit_log_immutability.py`.
- Template versioning + delete guard: `backend/app/api/routes/documents.py`, `tests/test_template_delete.py`.
- Idempotency (critical routes): `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`, `tests/test_documents_generate.py`.
- Outbox/webhooks: `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, `tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py`.
- Obligations/tasks: `backend/app/services/obligations.py`, `backend/app/api/routes/obligations.py`, `backend/app/api/routes/tasks.py`, `tests/integration/test_obligation_tasks.py`.

## 4) Verified run/test commands
- Discovery: `pytest --collect-only -q`.
- KPI and platform smoke tests:
  - `pytest -q tests/test_documents_generate.py tests/test_tenant_header_required.py tests/test_template_delete.py tests/test_webhooks_dispatch.py tests/test_risk_assessment_kpi5.py tests/test_outbox_dispatch.py`
- Frontend tests: `cd frontend && npm test -- --run`.
- Backend runability check: `PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8001` + `curl http://127.0.0.1:8001/health` (`200`).
- Frontend runability check: `cd frontend && npm run dev -- --host 127.0.0.1 --port 4173` + `curl http://127.0.0.1:4173` (`200`).
