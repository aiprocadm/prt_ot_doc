# CI / Test Recovery Plan

## Текущие workflow
- `.github/workflows/ci.yml`
  - `lint-and-static`
  - `backend-tests`
  - `frontend-tests`
  - `smoke-compose`

## Зафиксированные группы падений
1. **Проблемы окружения/настройки**
   - `make test-backend` падал локально до `make install` (не создана `.venv`).
   - `make test-smoke` падает без поднятого API/Docker Compose (`localhost:8000` недоступен).
2. **Проблемы миграций/БД**
   - `alembic upgrade heads` не выполняется в этом окружении без доступного Postgres host из `DATABASE_URL`.
3. **Проблемы тестов/архитектурного рассинхрона**
   - Интеграционные pipeline-тесты использовали несуществующие фикстуры (`client`, `tenant_headers`).
   - Тест зависимостей ожидал устаревший контракт (`AsyncSessionLocal`), тогда как используется `get_tenant_session`.
   - Тест PDF идемпотентности ожидал маршрут, который не был подключен в API роутере.
   - Тест header-engine ожидал watermark в `header1.xml`, но генератор обрезал строки после 3.

## Первопричины
- Дрейф тестов относительно фактической архитектуры API и DI.
- Неполная регистрация критичного PDF-роута в основном v1-роутере.
- Ограничение в `headers`-движке, которое ломало инвариант watermark.

## Блокирующие факторы
- Невозможность пройти часть backend-контуров из-за 5 “красных” тестов (`lastfailed`).
- Непредсказуемость smoke/migration шагов в среде без поднятых зависимостей.

## Выполненные исправления
- Исправлены интеграционные тесты pipeline на актуальные фикстуры (`async_client`, `make_auth_headers`).
- Обновлен DI-тест под фактический вызов `get_tenant_session(tenant, schema_name)`.
- Подключен PDF API router в `api/v1/router.py` под префикс `/files`.
- Исправлен `headers` engine: теперь обрабатывает все строки контента (включая watermark-строки сверх первых трех).

## План восстановления (приоритеты)
1. Must-pass: lint + backend focused + frontend CI.
2. Stabilize smoke (гарантированный `docker compose up` внутри job).
3. Отдельный DB migration gate на CI с явным ephemeral Postgres.
4. Уменьшение предупреждений frontend (`act(...)`, future flags React Router).
