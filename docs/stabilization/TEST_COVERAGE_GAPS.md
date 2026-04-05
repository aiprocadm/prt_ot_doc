# Пробелы покрытия тестами

**Обновлено:** 2026-04-05  

Соответствует **этапу 2** плана стабилизации: до крупного рефакторинга закрывать критичные зоны тестами.

### Матрица: ресурс × cross-tenant × ожидаемый HTTP

Условие: валидный JWT и `X-Tenant` = **аренда B**; сущность создана в **аренде A** (id известен).

| Ресурс | Маршрут (пример) | Ожидаемый статус | Тест / примечание |
|--------|------------------|------------------|-------------------|
| Job | `GET /api/v1/jobs/{id}` | **404** | `tests/test_jobs_api.py::test_get_job_returns_404_when_job_belongs_to_different_tenant` |
| Document | `GET /api/v1/documents/{id}` | **404** | `tests/integration/test_two_tenant_outbox_webhook_documents.py` (JWT совпадает с B) |
| Document batch | `GET /api/v1/documents/batch/{id}` | **404** | `tests/integration/test_cross_tenant_resource_matrix.py` (фильтр `tenant_id` в запросе) |
| File (v2) | `GET /api/v1/files/records/{id}` | **404** | `tests/integration/test_cross_tenant_resource_matrix.py` |
| Outbox (admin) | `GET /api/v1/admin/outbox/{id}` | **404** | `tests/integration/test_cross_tenant_resource_matrix.py` |
| Webhook delivery | `GET /api/v1/webhooks/deliveries/{id}/diagnostics` | **404** | `tests/integration/test_two_tenant_outbox_webhook_documents.py` |
| JWT tenant ≠ header tenant | любой маршрут с `ReadAccessDep` / `abac` | **403** tenant mismatch | `tests/test_rbac_abac.py` (`TENANT_SCOPE_MISMATCH` на `GET /api/v1/templates` и `POST /api/v1/companies`); `tests/test_tenant_security.py::test_header_token_tenant_mismatch_denied` |
| Template (legacy multipart) | `POST /api/v1/templates/{id}/versions` | **404** при `template.tenant_id` вне текущей аренды | `tests/integration/test_cross_tenant_resource_matrix.py::test_legacy_post_template_version_returns_404_for_other_tenant_template` |
| PWA offline batch | логика `OfflineSyncService.apply_batch` (briefing_entry) | батч **failed** + `tenant_scope_mismatch`, если entry не той аренды | `tests/services/test_training_briefings_next_services.py::test_offline_sync_fails_when_briefing_entry_other_tenant` |

Дополнительно: **retry vs terminal** для outbox/Celery — `docs/stabilization/RETRY_VS_TERMINAL_OUTBOX_CELERY.md`, контрактные проверки `tests/test_retry_terminal_contract.py`.

## Backend

| Область | Есть сейчас | Не хватает (приоритет) |
|---------|-------------|-------------------------|
| Tenant middleware | `test_middleware_tenant.py`, auth header | Автоматический чеклист при добавлении публичных префиксов |
| X-Tenant vs JWT / scope | `test_rbac_abac`, `test_tenant_security`, `test_auth_tenant_header_enforcement` | Держать в зелёном при смене `TenantMiddleware` / `rbac()` |
| Cross-tenant API (HTTP) | Матрица выше + outbox dispatch (два tenant) | Расширять таблицу при новых `enforce_row` / `get(PK)` |
| Protected routes / permission guards | `test_rbac_abac`, `test_next*` | Матрица роль × endpoint для критичных write-path |
| Background jobs happy/fail | `test_tasks_run_coroutine`, `test_tasks_pipeline_run_tenant_guard`, `test_next10_job_engine` | Контракт HTTP-классификации outbox + `RETRYABLE_EXCEPTIONS`: `tests/test_retry_terminal_contract.py` |
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

1. Неверный пароль / ошибка API при логине — `frontend/e2e/smoke.spec.ts` «login wrong password shows inline error» (нужен `E2E_USER_EMAIL`).
2. Документы: список и открытие карточки — в `smoke.spec.ts` при `E2E_USER_*`.
3. Минимальный путь generate + ожидание статуса (poll или один refresh) — в бэклоге.
4. Ограниченная роль: `E2E_LIMITED_USER_EMAIL` / `E2E_LIMITED_USER_PASSWORD` → экран «Доступ ограничен» на `/documents`.
5. Logout через меню пользователя (`data-testid="user-menu-trigger"`).

**Запуск:** `cd frontend && npm run e2e:install && E2E_START_SERVER=1 npm run e2e`. Для prod-бандла: `E2E_PREVIEW=1`.

## Contract / OpenAPI

- `tests/contract/test_openapi_contract.py`, `test_auth_openapi_runtime_contract.py` — держать в синхроне с `docs/openapi.yaml` при изменении публичных маршрутов.
