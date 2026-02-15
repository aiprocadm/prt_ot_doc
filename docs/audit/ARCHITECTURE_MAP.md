# ARCHITECTURE_MAP

## Backend (entrypoints, routing, middleware)
- Runtime entrypoint: `backend/app/main.py` (`app.main:app`).
- App factory + lifespan/bootstrap: `backend/app/api/app.py`.
- API v1 aggregation: `backend/app/api/v1/router.py`.
- Middleware chain in app factory:
  - `TenantMiddleware` (`backend/app/middleware/tenant.py`)
  - idempotency middleware (`_register_idempotency_middleware` in `backend/app/api/app.py`)
  - SlowAPI/rate limiting (`backend/app/core/rate_limit.py`)
  - observability/metrics (`backend/app/middleware/observability.py`, `backend/app/core/metrics.py`)

## Multi-tenant enforcement / isolation
- `X-Tenant` validation and 400 behavior: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`.
- Tenant-aware DB access via session scope and tenant schema mechanics: `backend/app/db/session.py`, `backend/app/db/__init__.py`.
- Frontend transport-level tenant header injection: `frontend/src/api/client.ts`, local tenant state in `frontend/src/stores/tenant.ts`.

## RBAC + ABAC
- AuthN/AuthZ dependencies and role checks: `backend/app/core/security.py`, `backend/app/api/dependencies.py`.
- ABAC policy tests: `tests/unit/test_abac_policies.py`, `tests/test_rbac_abac.py`.
- Role model/enum (owner/admin/specialists/etc.): `backend/app/models/models.py`.

## Audit (append-only)
- Audit model: `AuditLog` + update/delete guards in `backend/app/models/models.py`.
- Audit service + API usage: `backend/app/services/audit.py`, `backend/app/api/routes/audit.py`.
- Immutability tests: `tests/test_audit_log_immutability.py`, `tests/test_audit_log_api.py`.

## Documents/templates/versions + idempotency
- Document endpoints and generation flow: `backend/app/api/routes/documents.py`, `backend/app/api/v1/router.py`.
- Strict `(template_code, version)` and delete guard behavior validated by tests: `tests/test_template_delete.py`, `tests/test_documents_generate.py`.
- Idempotency storage + constraints: `IdempotencyKey` model in `backend/app/models/models.py`, service in `backend/app/services/idempotency.py`.

## Outbox + dispatcher + retries/dead-letter + metrics
- Outbox model/status/indexes: `backend/app/models/models.py`.
- Dispatcher/retry/backoff/dead-letter: `backend/app/services/outbox.py`.
- Webhook dispatch orchestration + timeout/retry outcomes: `backend/app/services/webhooks.py`.
- Coverage: `tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py`, `tests/test_webhook_routing.py`.

## Webhooks routing (global + per-tenant override)
- Global URL sets in settings: `backend/app/core/config.py`.
- Per-tenant subscriptions/override handling: `backend/app/services/webhooks.py`, `WebhookSubscription` model in `backend/app/models/models.py`.

## Obligations/tasks/deadlines
- Deadline generation and reminder processing: `backend/app/services/obligations.py`.
- Task service/state transitions: `backend/app/services/tasks.py`, routes in `backend/app/api/routes/tasks.py`.
- Integration coverage: `tests/integration/test_obligation_tasks.py`, `tests/unit/test_task_reminders.py`.

## Frontend map
- API client, auth headers, error handling: `frontend/src/api/client.ts`, `frontend/src/api/errorHandling.ts`.
- Tenant gate/context behavior: `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/stores/tenant.ts`.
- Auth/login flow: `frontend/src/pages/auth/LoginPage.tsx`, `frontend/src/stores/auth.ts`.
- Key pages: documents, tasks, dashboard in `frontend/src/pages/**`.

## Tests & discovery
- Backend pytest config (`testpaths`: `tests`, `integration_tests`): `pyproject.toml`.
- VS Code pytest discovery args: `.vscode/settings.json`.
- Frontend vitest: `frontend/vitest.config.ts`, `frontend/src/__tests__/**`.
