# Schema / Migration Test Audit

## Что проверено
- Тестовая схема создается с нуля в SQLite через metadata create_all.
- Критический idempotency-контур приведен к endpoint-scoped uniqueness.
- Проверен сценарий X-Tenant обязательности и idempotency replay через API-тесты.

## Риски/долги
- Нужно синхронизировать alembic-миграцию для PostgreSQL, чтобы убрать legacy unique `(tenant_id, key)` если она присутствует в DB.
- Рекомендуется добавить отдельный CI шаг `alembic upgrade heads` на чистой тестовой БД Postgres.

## Следующий шаг
- Зафиксировать миграцию на idempotency constraints и проверить `alembic heads`/upgrade/downgrade в CI.
