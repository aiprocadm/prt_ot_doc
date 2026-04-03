# Runbook: стабилизация и инциденты

## Быстрая диагностика API

1. **Сервис не стартует**
   - Логи: `app.startup` / `SettingsError` / `Missing required environment variables`.
   - Проверить `APP_ENV`: для `staging`/`production` — не должно быть `change-me`, `prt_local_*`, `S3_BACKEND=memory` (см. `CONFIGURATION_HARDENING.md`).

2. **400 TENANT_REQUIRED**
   - Клиент не передаёт `X-Tenant` на `/api/v1/*`.
   - Исключение: пути из `TenantMiddleware._public_prefixes` и системные `/health`.

3. **401 / массовый logout**
   - Проверить refresh, clock skew, истечение JWT.
   - Frontend: событие `app:auth-required` и `requestAuthRedirect`.

4. **Зависшие PDF / pipeline**
   - Celery worker logs, очередь `pdf` / `default`.
   - Задача `pipeline.watchdog` (beat) — проверить расписание в `celery_app.py`.

5. **Webhooks / outbox**
   - Таблица outbox: статусы, `attempts`, `next_retry_at`.
   - Логи доставки; дедупликация по idempotency / event id.

## Восстановление после сбоя

1. Не повторять опасные задачи без проверки idempotency key.
2. Для «застрявших» `in_progress` outbox — см. таймаут `OUTBOX_IN_PROGRESS_TIMEOUT_SECONDS`.
3. После деплоя: `alembic upgrade head`, smoke health, один бизнес-запрос с tenant header.

## Контакты и артефакты

- JUnit: `artifacts/backend-junit.xml` (CI).
- Docker smoke логи: артефакт `smoke-logs` при падении job `smoke-compose`.

## E2E (Playwright)

1. Один раз: `cd frontend && npm run e2e:install`.
2. Локально без бэкенда: `E2E_START_SERVER=1 npm run e2e` (поднимется Vite dev, проверяются логин-форма и редирект с защищённого маршрута).
3. Против уже запущенного стека: `E2E_BASE_URL=http://127.0.0.1:5173 npm run e2e` (порт подставить свой).
4. Полный логин: задать `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, при необходимости `E2E_TENANT`.
5. Регрессия **production** бандла: `E2E_PREVIEW=1 E2E_START_SERVER=1 npm run e2e` (дольше; учитывать PWA/SW).
6. CI: Actions → **E2E smoke (Playwright)** → Run workflow.
