# KNOWN LIMITATIONS (RC)

## Backend / migrations
- Локальный smoke-контур в dockerless режиме блокируется конфликтом SQLite-миграций на `initial schema` (`table already exists`) при `alembic upgrade heads`.
- Полный backend regression (`pytest -q` весь репозиторий) в этом цикле не завершен, поэтому остаются риски вне критичного среза.

## Integrations
- В окружении отсутствует `soffice`, поэтому PDF-контур зависит от fallback-логики и не эквивалентен production LibreOffice-пайплайну.
- Полноценные e2e потоки, завязанные на внешний infra-контур, требуют отдельного интеграционного стенда.

## Frontend / e2e
- Lint/test/build стабильны, но браузерный e2e фронт+бэк сценарий в этом цикле не выполнялся.
