# CI STABILIZATION REPORT (RC)

## Что было нестабильно
- `scripts/smoke.sh` не был пригоден для dockerless CI/RC прогонов.
- Smoke зависел от заранее поднятого API и docker compose `api exec`.
- Локальный миграционный шаг smoke падает с конфликтом `initial schema` на SQLite (`table already exists`).

## Что исправлено
1. Переписан smoke-скрипт на dual-mode (docker-compose и dockerless):
   - автоподъем API для локального RC;
   - fallback для PDF probe без `docker compose exec`;
   - более безопасная диагностика при недоступном API.
2. Повторно подтверждена стабильность backend critical test-среза.
3. Повторно подтверждена стабильность frontend lint/test/build.

## Что стабильно в текущем прогоне
- `./scripts/pytest.sh tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py tests/test_health_ready.py`
- `cd frontend && npm run lint`
- `cd frontend && npm run test -- --run`
- `cd frontend && npm run build`

## Что остается нестабильным
- `./scripts/smoke.sh` все еще падает на этапе миграций в локальном sqlite контуре (`initial schema` conflict).
- Полный `pytest -q` по всему репозиторию не закрыт в рамках этого цикла и должен быть прогнан в CI runner отдельно.
- Реальные внешние интеграции (полный PDF/infra слой) зависят от доступности окружения.
