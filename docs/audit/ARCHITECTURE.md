# Architecture Map (Discovery)

## 1) Repository structure
- `backend/` — FastAPI API, domain services, SQLAlchemy models, Alembic migrations, Celery worker/tasks.
- `frontend/` — React + Vite SPA, Zustand stores, API client with auth/tenant interceptors, vitest tests.
- `infra/`, `docker-compose.yml`, `.devcontainer/` — docker and Codespaces bootstrap.
- `tests/` + `frontend/src/__tests__/` — backend + frontend test suites.

## 2) Entry points

### Backend
- ASGI entry: `backend/app/main.py` → `create_app()` from `app.api.app`.
- App factory and middleware wiring: `backend/app/api/app.py`.
- API v1 router assembly: `backend/app/api/v1/router.py`.
- Tenant middleware: `backend/app/middleware/tenant.py`.
- Runtime settings/bootstrap: `backend/app/core/config.py`.

### Workers / async delivery
- Celery worker bootstrap: `backend/app/worker.py`.
- Celery app and queues: `backend/app/services/celery_app.py`.
- Outbox dispatcher + retries/dead-letter: `backend/app/services/outbox.py` (`OutboxProcessor.process_once`).
- Task scheduling/reminders hooks: `backend/app/tasks.py`, `backend/app/services/tasks.py`, `backend/app/services/obligations.py`.

### Frontend
- SPA bootstrap: `frontend/src/main.tsx`.
- Route tree: `frontend/src/router/AppRouter.tsx`.
- Tenant gate/context UX: `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/stores/tenant.ts`.
- API client with auth refresh + tenant header enforcement: `frontend/src/api/client.ts`.

## 3) Cross-cutting capability map
- Tenant enforcement:
  - backend: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`, tenant-aware repository filters in routes/services.
  - frontend: `frontend/src/api/client.ts` rejects `/v1` requests without active tenant.
- RBAC + ABAC:
  - policies/dependencies: `backend/app/core/security.py`.
  - usage in routes: e.g. `backend/app/api/routes/risk.py`, `backend/app/api/routes/documents.py`, `backend/app/api/routes/tasks.py`.
- Audit log:
  - write service: `backend/app/services/audit.py`, `backend/app/domains/audit/service.py`.
  - API and immutability checks: `backend/app/api/routes/audit.py`, `tests/test_audit_log_immutability.py`.
- Templates/versioning:
  - models/schemas/routes: `backend/app/models/document.py`, `backend/app/schemas/template.py`, `backend/app/api/routes/documents.py`.
  - delete guard tests: `tests/test_template_delete.py`.
- Idempotency:
  - middleware+store: `backend/app/core/idempotency.py`, `backend/app/services/idempotency.py`.
  - endpoint usage: documents + risk assess.
- Outbox/webhooks:
  - enqueue/dispatch/retry/DLQ: `backend/app/services/outbox.py`.
  - routing global + tenant overrides: `backend/app/services/webhooks.py`, `backend/app/models/models.py` (`WebhookSubscription`).
- Obligations/tasks:
  - domain + API: `backend/app/services/obligations.py`, `backend/app/api/routes/obligations.py`, `backend/app/api/routes/tasks.py`.

## 4) Run and test commands
- Primary make targets: `make dev:lite`, `make test:lite`, `make dev`, `make test`, `make test-frontend`, `make migrate`.
- Dockerless helper scripts: `scripts/dev_lite.sh`, `scripts/test_lite.sh`, `scripts/dockerless_env.sh`.
- Pytest discovery in Codespaces: `.vscode/settings.json`, `vscode_pytest.py`.
