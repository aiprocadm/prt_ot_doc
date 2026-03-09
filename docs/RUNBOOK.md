# RUNBOOK

## Локальный запуск
1. `cp .env.example .env`
2. `make install`
3. `make migrate`
4. `make dev-lite` (или `make up` для docker)

## Backend
- Запуск API: `make run`
- Миграции: `make migrate`
- Tenant migration: `make tenant-migrate TENANT=<slug>`

## Frontend
- `cd frontend && npm ci`
- `cd frontend && npm run dev`
- Проверки: `npm run lint && npm run test && npm run build`

## Critical tests
- `make codex-audit`
- либо точечно:
  - `python -m pytest tests/test_tenant_header_required.py tests/test_tenant_security.py -q`
  - `python -m pytest tests/test_webhooks_dispatch.py -q`

## Проверка pipeline
- API routes в `/api/v1/pipelines/*`, `/api/v1/packs/*`, `/api/v1/replace/*`.
- Для smoke: `python -m pytest tests/test_next23_pipelines.py -q`

## Проверка tenant enforcement
- Без `x-tenant` на business route должен быть `400`.
- Тесты: `tests/test_tenant_header_required.py`, `tests/test_next39_tenancy_enforcement.py`.

## Проверка portal/admin путей
- FE routes: `/client-portal/*`, `/admin/*`.
- Убедиться, что `ProtectedRoute` и permissions включены.

## Health/readiness/logs/jobs
- Health: `/health`, `/ready`, `/healthz`, `/readyz`.
- Jobs: `/api/v1/jobs`, `/api/v1/pipelines/runs`.
- Логи docker: `make logs`.
