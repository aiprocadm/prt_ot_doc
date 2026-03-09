# RUNBOOK

## Локальный запуск
1. `cp .env.example .env`
2. Для Codespaces/dev-lite: `make cs:dev`
3. Для полного docker-compose: `make up`

## Backend
- Запуск: `make run` (или через `make cs:dev`).
- Health: `GET /health`, readiness: `GET /readyz`.

## Frontend
- Запуск в dev-lite поднимается скриптом `make cs:dev`.
- Отдельно: `make frontend-install` и `cd frontend && npm run dev`.

## Критические тесты
- Полный критический срез: `make codex-audit`.
- Базовый regression: `make cs:test`.

## Проверка документного pipeline
- Тесты: `python -m pytest tests/test_templates_pipeline_api.py tests/test_documents_status_flow.py -q`.
- Проверить dry-run/apply replace и переходы статусов.

## Проверка tenancy требований
- `python -m pytest tests/test_tenant_header_required.py tests/test_tenant_security.py tests/test_next39_tenancy_enforcement.py -q`.

## Проверка portal/admin путей
- API: `python -m pytest tests/test_client_portal_api.py tests/test_tenant_security.py -q`.
- UI: открыть `/client-portal`, `/admin` и убедиться в role guards.

## Состояние, логи, задания
- Логи docker: `make logs`.
- Очереди/jobs: `python -m pytest tests/test_jobs_api.py tests/test_projection_jobs.py -q`.
- Фоновый worker: `backend/app/worker.py` (Celery).
