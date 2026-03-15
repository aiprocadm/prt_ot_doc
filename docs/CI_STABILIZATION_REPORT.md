# CI STABILIZATION REPORT (RC)

## Что было нестабильно
- `scripts/smoke.sh` не был пригоден для dockerless CI/RC прогонов.
- Smoke зависел от заранее поднятого API и docker compose `api exec`.
- Локальный миграционный шаг smoke падал на SQLite из-за PostgreSQL-типа `JSONB` в ревизиях (`UnsupportedCompilationError`).

## Что исправлено
1. Переписан smoke-скрипт на dual-mode (docker-compose и dockerless):
   - автоподъем API для локального RC;
   - fallback для PDF probe без `docker compose exec` и безопасный skip при отсутствии `soffice`;
   - более безопасная диагностика при недоступном API.
2. Добавлен fallback smoke-gate для dockerless:
   - при ожидаемой несовместимости SQLite/JSONB в Alembic smoke не падает аварийно;
   - выполняется минимальный обязательный срез проверок (`tests/test_health_ready.py`, `tests/test_tenant_header_required.py`).
3. Повторно подтверждена стабильность backend critical test-среза.
4. Повторно подтверждена стабильность frontend lint/test/build.

## Что стабильно в текущем прогоне
- `./scripts/pytest.sh tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py tests/test_health_ready.py`
- `cd frontend && npm run lint`
- `cd frontend && npm run test -- --run`
- `cd frontend && npm run build`

## Что остается нестабильным
- Полный путь `alembic upgrade heads` в sqlite-контуре остается ограниченным из-за использования `JSONB` в части ревизий; в RC используется fallback-gate.
- Полный `pytest -q` по всему репозиторию не закрыт в рамках этого цикла и должен быть прогнан в CI runner отдельно.
- Реальные внешние интеграции (полный PDF/infra слой) зависят от доступности окружения.
