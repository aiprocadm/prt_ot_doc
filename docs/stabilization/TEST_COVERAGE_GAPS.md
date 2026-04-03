# Пробелы покрытия тестами

## Backend

| Область | Есть сейчас | Не хватает |
|---------|-------------|------------|
| Tenant middleware | `test_middleware_tenant.py`, auth header tests | Автоматический тест на каждый новый публичный префикс |
| Cross-tenant API | Частично (S3 keys) | HTTP integration: запрос ресурса чужого `tenant_id` → 404/403 |
| Outbox / webhooks | Есть частично в tests | Дедуп webhook, poison message, terminal retry |
| Pipelines / Celery | Unit частично | Идемпотентный rerun с фикстурой БД |
| Migrations | Alembic heads | Тест «upgrade head» на чистой БД в CI (опционально job) |

## Frontend

| Область | Есть сейчас | Не хватает |
|---------|-------------|------------|
| Auth redirect | `errorHandlingAuthRedirect.test.ts` | Bootstrap store + router integration |
| Permissions vs routes | `routeGroups.test.tsx` и др. | Матрица «роль → видимость пункта меню» |
| Крупные формы | Точечные тесты | Visual/regression по критичным wizard-шагам |

## E2E (Playwright)

**Статус:** не внедрён в CI (намеренно в этом спринте).

**Минимальный набор для следующего этапа:**

1. Login (happy / wrong password).
2. Запрос с `X-Tenant` (или UI выбора tenant, если есть).
3. Documents: список / открытие (mock или test tenant).
4. 403: пользователь без права → ожидаемый redirect/страница.

## Contract / OpenAPI

- `tests/contract/test_openapi_contract.py`, `test_auth_openapi_runtime_contract.py` — поддерживать синхронно с `docs/openapi.yaml`.
