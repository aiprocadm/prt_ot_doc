# Runbook: стабилизация и инциденты

**Обновлено:** 2026-04-14  

## Быстрая диагностика API

1. **Сервис не стартует**
   - Логи: `app.startup` / `SettingsError` / missing env.
   - Проверить `APP_ENV`: для `staging`/`production` — см. `CONFIGURATION_HARDENING.md`.

2. **400 TENANT_REQUIRED**
   - Клиент не передаёт `X-Tenant` на `/api/v1/*`.
   - Исключение: пути из `TenantMiddleware._public_prefixes` и `/health`.

2b. **403 TENANT_SCOPE_MISMATCH**
   - JWT `tenant` не совпадает с резолвом `X-Tenant` (slug, `code` или UUID в заголовке).
   - Регрессия: `tests/test_jwt_xtenant_uuid_scope_mismatch.py`, `tests/test_tenant_security.py`.

3. **401 / массовый logout**
   - Refresh, clock skew, истечение JWT.
   - Frontend: `app:auth-required`, `requestAuthRedirect`.

4. **Structured API errors**
   - Ожидаемый контракт (целевой): `code`, `type`, `message`, `details`, `field_errors`, `correlation_id`.
   - Если клиент получает строку вместо объекта — проверить версию `error_handlers` и формат исключения.

5. **403 / 404 на своём ресурсе после деплоя**
   - Проверить, что в сессии выставлены `tenant_id` / `tenant_slug` (middleware + dependency).
   - Логи с суффиксом `*_tenant_scope_mismatch` — несоответствие строки модели и контекста сессии; не ретраить без исправления данных/аргументов задачи.

6. **Зависшие PDF / pipeline**
   - Celery worker logs, очереди.
   - `pipeline.watchdog` (beat) — расписание в `celery_app.py`.
   - `pipeline.run.tenant_scope_mismatch` / `job_not_found` при валидном id: неверный `tenant_slug` в kwargs задачи.

7. **Webhooks / outbox**
   - Статусы, `attempts`, `next_retry_at`, poison / dead.
   - Дедупликация по idempotency / event id.

## Восстановление после сбоя

1. Не повторять опасные задачи без проверки idempotency key.
2. «Застрявшие» in-progress outbox — см. `OUTBOX_IN_PROGRESS_TIMEOUT_SECONDS` (если задано).
3. После деплоя: `alembic upgrade head`, health, один бизнес-запрос с tenant header.

## Наблюдаемость (этап 10)

- Искать по `correlation_id` от клиента через API-логи и worker-логи.
- В worker-задачах при расследовании проверять наличие `tenant_slug` / `tenant_id` в `extra`.
- Не логировать PII (паспорт, email в payload) — в коде уже есть санитизация в отдельных путях; новые логи проходить чеклист.

## Контакты и артефакты

- JUnit: `artifacts/backend-junit.xml` (если включено в CI).
- Docker smoke: артефакты логов при падении job.

## E2E (Playwright)

1. Один раз: `cd frontend && npm run e2e:install`.
2. Локально: `E2E_START_SERVER=1 npm run e2e`.
3. Против своего URL: `E2E_BASE_URL=... npm run e2e`.
4. Полный логин: `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, при необходимости `E2E_TENANT`.
5. Prod-бандл: `E2E_PREVIEW=1 E2E_START_SERVER=1 npm run e2e`.
6. CI: workflow **E2E smoke (Playwright)** при необходимости.

## Связанные документы

- Риски релиза: `REGRESSION_RISKS_AND_MITIGATIONS.md`
- Пробелы тестов: `TEST_COVERAGE_GAPS.md`
- Аудит: `STABILIZATION_AUDIT.md`
