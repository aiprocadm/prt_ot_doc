# Пробелы покрытия тестами

**Обновлено:** 2026-04-04  

Соответствует **этапу 2** плана стабилизации: до крупного рефакторинга закрывать критичные зоны тестами.

## Backend

| Область | Есть сейчас | Не хватает (приоритет) |
|---------|-------------|-------------------------|
| Tenant middleware | `test_middleware_tenant.py`, auth header | Автоматический чеклист при добавлении публичных префиксов |
| X-Tenant vs JWT / scope | `test_auth_tenant_header_enforcement`, `test_tenant_security` | Явный сценарий «токен аренды A + header B» → 400/403 |
| Cross-tenant API (HTTP) | Частично (S3 keys, guards); **GET `/jobs/{id}`** — `test_jobs_api.test_get_job_returns_404_when_job_belongs_to_different_tenant` | Таблица: resource × чужой id × ожидаемый 404/403 для documents, files, batch, outbox |
| Protected routes / permission guards | `test_rbac_abac`, `test_next*` | Матрица роль × endpoint для критичных write-path |
| Background jobs happy/fail | `test_tasks_run_coroutine`, `test_tasks_pipeline_run_tenant_guard`, `test_next10_job_engine` | Явные тесты terminal failure vs retry для 2–3 ключевых задач |
| Pipeline orchestrator | `backend/tests/test_next39_pipeline_orchestrator.py` | Интеграция с реальной БД-фикстурой tenant + template (если отличается от unit) |
| Outbox dispatch | `test_outbox_dispatch`, `test_next43_outbox_webhooks` | Два tenant: событие одного не видно/не обрабатывается в контексте другого |
| Webhook deduplication | Частично | Повтор того же delivery id / payload — идемпотентность |
| Idempotency (documents.generate, jobs) | `test_services_idempotency_unit`, `test_next10_job_engine` | HTTP integration 409 mismatch + повтор 202 с тем же телом |
| Document generation / readiness | `test_documents_generate`, `test_document_readiness_unit` | Compare/dependency-map endpoints под двумя версиями (integration) |
| Unauthorized / forbidden | Разрозненно | Один модуль «smoke security»: 401 без токена, 403 роль, 404 cross-tenant |
| `enforce_row_belongs_to_tenant` (jobs, files, webhooks) | Косвенно через маршруты | Явные тесты на mismatch → ожидаемый статус и отсутствие утечки полей |

## Frontend

| Область | Есть сейчас | Не хватает |
|---------|-------------|------------|
| Auth redirect | `errorHandlingAuthRedirect.test.ts` | Bootstrap store + router (без дублирования) |
| Stale token / logout | Частично | После logout запрос не несёт старый access; редирект |
| Permissions vs routes | `routeGroups.test.tsx` | Матрица «роль → пункт меню / кнопка» для OT-критичных экранов |
| Polling / mutations | `usePolling` и др. | Граничные случаи: unmount во время poll, double fetch |

## E2E (Playwright)

**Статус:** каркас в репозитории; полный прогон часто в отдельном workflow.

**Уже есть (`frontend/e2e/smoke.spec.ts`):**

- Страница логина (видимость полей).
- Редирект с защищённого маршрута без сессии.
- Условный happy-path при `E2E_USER_EMAIL` / `E2E_USER_PASSWORD`.

**Целевой минимум для регрессии (этап 8):**

1. Неверный пароль / ошибка API при логине.
2. Документы: список и открытие карточки (при поднятом API).
3. Минимальный путь generate + ожидание статуса (poll или один refresh).
4. 403 / экран «нет доступа» под ограниченной ролью.
5. Logout и повторный заход.

**Запуск:** `cd frontend && npm run e2e:install && E2E_START_SERVER=1 npm run e2e`. Для prod-бандла: `E2E_PREVIEW=1`.

## Contract / OpenAPI

- `tests/contract/test_openapi_contract.py`, `test_auth_openapi_runtime_contract.py` — держать в синхроне с `docs/openapi.yaml` при изменении публичных маршрутов.
