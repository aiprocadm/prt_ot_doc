# RUNBOOK

## Локальный запуск
1. `cp .env.example .env`
2. `make cs:dev` (предпочтительно для локальной разработки)
3. Альтернатива: `make up` для полного docker-compose стека.

## Backend
- API стартует через `make run` (или в составе `make cs:dev`).
- Проверки состояния:
  - `GET /health`
  - `GET /readyz`

## Frontend
- В dev-lite: поднимается из `make cs:dev`.
- Отдельно: `make frontend-install && cd frontend && npm run dev`.

## Критические проверки (sanity)
- Основная агрегированная команда: `make codex-audit`.
- Быстрый профиль по документам/идемпотентности/арендатору:
  - `pytest -q tests/test_documents_generate.py tests/test_template_delete.py tests/integration/test_idempotency_generate.py tests/test_tenant_header_required.py`

## Проверка документного конвейера
- `pytest -q tests/test_templates_pipeline_api.py tests/test_documents_status_flow.py`
- Проверять: корректные статусы, dry-run/apply replace, запрет удаления используемой версии шаблона.

## Проверка требований арендатора
- `pytest -q tests/test_tenant_header_required.py tests/test_tenant_security.py tests/test_auth_tenant_header_enforcement.py tests/test_middleware_tenant.py tests/test_next39_tenancy_enforcement.py`
- Ожидаемое: business route без `X-Tenant` → 400; межарендный доступ запрещён.

## Portal/Admin
- API regression: `pytest -q tests/test_client_portal_api.py tests/test_tenant_security.py`
- Ручная проверка: `/client-portal`, `/admin` + role guards.

## Логи, задания, очереди
- `make logs`
- `pytest -q tests/test_jobs_api.py tests/test_projection_jobs.py`
- Worker entrypoint: `backend/app/worker.py`.


### Hotfix-проверка auth tenant enforcement
- `pytest -q tests/test_auth_tenant_header_enforcement.py`
- Ожидаемое: `/api/v1/auth/me` и `/api/v1/auth/refresh` без `X-Tenant` => `400 TENANT_REQUIRED`; `/api/v1/auth/login` без `X-Tenant` остается доступным публичным endpoint (но без tenant-контекста возвращает `401` на валидные tenant-specific credentials).

- Для быстрой проверки tenant-safe inbound webhook контура: `pytest -q tests/test_inbound_webhook_tenant_context.py`.
