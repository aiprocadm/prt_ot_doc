# Architecture Map (backend + frontend + infra)

## Runtime contours

### Backend (FastAPI)
- Entry: `backend/app/main.py` → `backend/app/api/app.py#create_app`.
- API composition: `backend/app/api/v1/router.py` mounts business routers under `/api/v1`.
- Tenant enforcement chain:
  - HTTP middleware: `backend/app/middleware/tenant.py`
  - tenant context/dependencies: `backend/app/core/tenant.py`, `backend/app/api/dependencies.py`
- Domain services: `backend/app/services/*` + `backend/app/domains/*`.
- Persistence: SQLAlchemy models under `backend/app/models/*`, async engine/session in `backend/app/db/session.py`.

### Async/events
- Celery tasks: `backend/app/tasks.py`, worker bootstrap `backend/app/worker.py`.
- Outbox dispatcher/retries/dead-letter/metrics: `backend/app/services/outbox.py`.
- Webhook routing and per-tenant override: `backend/app/services/webhooks.py`.
- Idempotency guard for command routes: `backend/app/core/idempotency.py` + middleware registration in app factory.

### Frontend (React/Vite)
- Entry: `frontend/src/main.tsx`.
- Router and protected pages: `frontend/src/router/AppRouter.tsx`, `frontend/src/router/ProtectedRoute.tsx`.
- Tenant guard:
  - API interceptor: `frontend/src/api/client.ts`
  - tenant gate UI: `frontend/src/components/tenant/TenantGate.tsx`
  - store: `frontend/src/stores/tenant.ts`
- Role/permission UI controls: `frontend/src/components/permissions/*`, `frontend/src/permissions/*`.

### Infra/DevX
- Codespaces: `.devcontainer/devcontainer.json`, `.devcontainer/post-create.sh`.
- Dockerless scripts: `scripts/dev_lite.sh`, `scripts/test_lite.sh`, `scripts/dockerless_env.sh`.
- Docker mode: `docker-compose.yml` + `Makefile` (`make dev`, `make test`).
- CI: `.github/workflows/ci.yml`.

## Critical flow map
1. **Document generation**
   - `POST /api/v1/documents/generate`
   - checks: tenant header + idempotency key
   - pipeline service creates document/version and emits outbox events
   - outbox dispatcher sends webhooks (`DocumentGenerated`, etc.)
2. **Risk assessment**
   - `POST /api/v1/risk/assess`
   - deterministic calc (`domains/risk/calc.py`) + creates risk cards/action plan
   - event recorded for integration/webhook path
3. **Dev admin bootstrap**
   - startup hook (`api/app.py` lifespan) invokes `services/dev_bootstrap.py`
   - active only in `development/test` and only with env switch

## Verified commands used in this audit cycle
- `pytest --collect-only -q`
- `cd frontend && npm test`
- `./scripts/configure_dockerless_env.sh .env`
- `source ./scripts/dockerless_env.sh && PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000`
