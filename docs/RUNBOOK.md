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
- Проверка диагностики интеграций и provider mode: `pytest -q backend/tests/test_corporate_readiness_hardening.py`
- Проверка PWA bootstrap/offline contract: `pytest -q backend/tests/test_pwa_sync_bootstrap.py`
- `make logs`
- `pytest -q tests/test_jobs_api.py tests/test_projection_jobs.py`
- Worker entrypoint: `backend/app/worker.py`.


### Hotfix-проверка auth tenant enforcement
- `pytest -q tests/test_auth_tenant_header_enforcement.py`
- Ожидаемое: `/api/v1/auth/me` и `/api/v1/auth/refresh` без `X-Tenant` => `400 TENANT_REQUIRED`; `/api/v1/auth/login` без `X-Tenant` остается доступным публичным endpoint (но без tenant-контекста возвращает `401` на валидные tenant-specific credentials).

- Для быстрой проверки tenant-safe inbound webhook контура: `pytest -q tests/test_inbound_webhook_tenant_context.py`.

## Проверка защиты от обхода tenant middleware
- Запуск: `pytest -q tests/test_middleware_tenant.py::test_tenant_middleware_requires_header_for_non_docs_openapi_suffix_path`
- Ожидаемое: путь `/api/v1/templates/openapi.json` без `X-Tenant` возвращает `400 TENANT_REQUIRED`.

## Проверка безопасного TTL presigned download URL
- Запуск: `PYTHONPATH=backend pytest -q tests/test_core_config_utils.py::test_presign_download_ttl_is_bounded`
- Ожидаемое: значения `PRESIGN_DOWNLOAD_TTL_SECONDS` ниже 60 и выше 3600 отклоняются валидацией конфигурации.


## Быстрая проверка hardening client portal
- `pytest -q tests/test_next62_analytics_search_export_center.py::test_client_user_cannot_patch_internal_portal_requests`
- Ожидаемое: `403` для роли `client_user` на `PATCH /api/v1/portal-requests/{id}`.
