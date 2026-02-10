# Architecture Map (Discovery)

## 1) Repository structure
- `backend/` — FastAPI API (`app/main.py`), domain services, SQLAlchemy models, Alembic migrations, Celery worker/tasks.
- `frontend/` — React + Vite SPA, tenant store, API client interceptors, vitest tests.
- `infra/`, `.devcontainer/`, `docker-compose.yml` — containerized and Codespaces bootstrap.
- `tests/` + `frontend/src/__tests__/` — backend/frontend automated suites.

## 2) Entry points

### Backend
- ASGI entrypoint: `backend/app/main.py` (`app = create_app()`).
- App factory + middleware/bootstrap: `backend/app/api/app.py`.
- v1 router assembly: `backend/app/api/v1/router.py`.
- Tenant enforcement middleware: `backend/app/middleware/tenant.py` + tenant deps in `backend/app/core/tenant.py`.
- Runtime settings: `backend/app/core/config.py`.

### Workers / async delivery
- Celery worker bootstrap: `backend/app/worker.py`.
- Celery app config: `backend/app/services/celery_app.py`.
- Outbox dispatcher/retry/dead-letter: `backend/app/services/outbox.py`.
- Scheduled obligations/reminders hooks: `backend/app/tasks.py`, `backend/app/services/tasks.py`, `backend/app/services/obligations.py`.

### Frontend
- SPA bootstrap: `frontend/src/main.tsx`.
- Route tree: `frontend/src/router/AppRouter.tsx`.
- Tenant UX gate + store: `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/stores/tenant.ts`.
- API client (`X-Tenant` injection + block without tenant): `frontend/src/api/client.ts`.

## 3) Cross-cutting capability map
- **Tenant enforcement:**
  - backend: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`.
  - frontend: `frontend/src/api/client.ts` blocks `/v1` calls without tenant context.
- **RBAC + ABAC:** `backend/app/core/security.py` + route usage (`backend/app/api/routes/risk.py`, `documents.py`, `tasks.py`).
- **Audit append-only:** `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`.
- **Template versioning and delete guard:** `backend/app/models/document.py`, `backend/app/api/routes/documents.py`.
- **Idempotency:** `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`.
- **Outbox + webhooks:** `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`, model `WebhookSubscription` in `backend/app/models/models.py`.
- **Obligations/tasks registry:** `backend/app/services/obligations.py`, `backend/app/api/routes/obligations.py`, `backend/app/api/routes/tasks.py`.

## 4) Commands (run/test)
- Backend (dockerless): `make dev:lite`
- Backend + infra (docker): `make dev`
- Test suites: `make test:lite`, `make test`, `make test-frontend`
- Migrations: `make migrate`
- Pytest discovery / Codespaces Testing panel: `pytest --collect-only -q` with config in `.vscode/settings.json`.
