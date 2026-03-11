# Schema / Migration Test Audit

## Выполненные проверки
- `alembic heads` выполнен: обнаружено несколько head-веток (мульти-ветвление миграций).
- Backend тесты используют test schema через SQLAlchemy metadata/fixture контур.
- Проверен критичный DI путь tenant-session (через unit test `test_get_session_uses_tenant_session_factory`).

## Результаты
- **Heads присутствуют и читаются корректно**, но требуют согласованного migration plan при дальнейшем rebasing.
- `alembic upgrade heads` в текущем окружении **не воспроизведен** из-за недоступного Postgres host (`socket.gaierror`).

## Обязательные поля/инварианты (проверенные косвенно тестами)
- Tenant-aware session routing.
- Idempotency endpoint для PDF с обязательным `Idempotency-Key`.
- Pipeline idempotency на уровне API.

## Рекомендации
1. Добавить отдельный CI job `schema-migrations` с сервисом Postgres.
2. Включить проверки:
   - `alembic upgrade heads`
   - (опционально) `alembic downgrade -1 && alembic upgrade heads`
3. Добавить smoke-проверку обязательных tenant-индексов и soft-delete полей через SQL introspection test.
