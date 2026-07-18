# ARCHITECTURE_MAP

## Backend
- Entrypoint: `backend/app/main.py` (`app.main:app`).
- App factory + lifespan: `backend/app/api/app.py` (`create_app`, `_create_lifespan`).
- Middleware chain: tenant (`backend/app/middleware/tenant.py`), idempotency (`app/api/app.py`), rate-limit (`backend/app/core/rate_limit.py`), observability (`backend/app/middleware/observability.py`).
- DB/session: `backend/app/db/session.py` (`configure_engine`, `session_scope`, dispose).
- Alembic: `backend/app/migrations/*`.

## Документы / pipeline
- DOCX/PDF сервисы: `backend/app/services/docx.py`, `backend/app/services/pdf.py`, `backend/app/services/pipeline.py`.
- Основные API маршруты документов: `backend/app/api/routes/documents.py`, `backend/app/api/routes/templates.py`.
- KPI тесты по идемпотентности/шаблонам: `tests/test_idempotency.py`, `tests/test_template_delete.py`.

## Outbox / webhooks / tasks
- Outbox dispatcher + retries/dead-letter: `backend/app/services/outbox.py`.
- Webhooks routing/dispatch: `backend/app/services/webhooks.py`.
- Task orchestration: `backend/app/services/tasks.py`.
- Проверки: `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py`.

## Dev bootstrap
- Bootstrap admin: `backend/app/services/dev_bootstrap.py`.
- Вызов на старте приложения: `backend/app/api/app.py` (lifespan, `await bootstrap_admin_user(settings)`).

## Frontend
- Vite proxy `/api` → backend: `frontend/vite.config.ts`.
- Runtime env: `frontend/src/config/env.ts`.
- API client + tenant header guard: `frontend/src/api/client.ts`.
- Tenant UX gate: `frontend/src/components/tenant/TenantGate.tsx`.

## DevX scripts
- Dev start: `scripts/dev_lite.sh`.
- Test run: `scripts/test_lite.sh`.
- Env tuning: `scripts/configure_dockerless_env.sh`, `scripts/dockerless_env.sh`.
- Pytest wrapper: `scripts/pytest.sh`.

## Tests & discovery
- Backend testpaths: `tests`, `integration_tests` (`pyproject.toml`, `.vscode/settings.json`).
- Discovery defaults: `test_env_defaults.py`, `sitecustomize.py`, `vscode_pytest.py`.
- KPI coverage: `tests/test_idempotency.py`, `tests/test_tenant_header_required.py`, `tests/test_template_delete.py`, `tests/test_outbox_dispatch.py`, `tests/test_risk_assessment_kpi5.py`.
