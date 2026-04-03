# Пробелы покрытия тестами

## Backend

| Область | Есть сейчас | Не хватает |
|---------|-------------|------------|
| Tenant middleware | `test_middleware_tenant.py`, auth header tests | Автоматический тест на каждый новый публичный префикс |
| Cross-tenant API | Частично (S3 keys) | HTTP integration: запрос ресурса чужого `tenant_id` → 404/403 |
| Outbox / webhooks | Есть частично в tests | Дедуп webhook, poison message, terminal retry |
| Pipelines / Celery | Unit частично; `_run_coroutine` — `test_tasks_run_coroutine.py`; tenant guard run — `test_tasks_pipeline_run_tenant_guard.py` | Те же guard’ы для batch/job путей; идемпотентный rerun; интеграция «два tenant» для outbox/webhook |
| Migrations | Alembic heads | Тест «upgrade head» на чистой БД в CI (опционально job) |

## Frontend

| Область | Есть сейчас | Не хватает |
|---------|-------------|------------|
| Auth redirect | `errorHandlingAuthRedirect.test.ts` | Bootstrap store + router integration |
| Permissions vs routes | `routeGroups.test.tsx` и др. | Матрица «роль → видимость пункта меню» |
| Крупные формы | Точечные тесты | Visual/regression по критичным wizard-шагам |

## E2E (Playwright)

**Статус:** каркас в репозитории; в основном `ci.yml` не включён (отдельный workflow `e2e-smoke.yml`, ручной запуск).

**Уже есть (`frontend/e2e/smoke.spec.ts`):**

- Страница логина (видимость полей).
- Редирект с `/documents` на `/auth/login` без сессии.
- Условный happy-path логина при `E2E_USER_EMAIL` / `E2E_USER_PASSWORD`.

**Запуск:** `cd frontend && npm run e2e:install && E2E_START_SERVER=1 npm run e2e` (dev). Для prod-сборки: `E2E_PREVIEW=1 E2E_START_SERVER=1 npm run e2e`.

**Следующий этап:**

1. Login (wrong password / ошибка API).
2. Документы: список / карточка при поднятом бэкенде.
3. 403 / `no-access` под отдельной ролью.
4. Logout и повторный заход.

## Contract / OpenAPI

- `tests/contract/test_openapi_contract.py`, `test_auth_openapi_runtime_contract.py` — поддерживать синхронно с `docs/openapi.yaml`.
