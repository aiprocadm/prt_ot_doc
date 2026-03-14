# CI STABILIZATION REPORT (RC)

## Что было нестабильно
- Интеграционный тест WS-stub конфликтовал с tenancy-контрактом (`400` vs `501`).
- Потенциально нестабильный backend прогон из-за длинного полного `pytest` и наличия infra-зависимых частей.
- Миграционный этап зависит от доступности внешнего PostgreSQL хоста в окружении.

## Что исправлено
1. Обновлен `tests/integration/test_ws_stub.py`:
   - проверка `400` без `X-Tenant`;
   - проверка `501` при `X-Tenant`.
2. Проведен повторный набор критических проверок backend/frontend после правки.

## Что теперь стабильно (локально)
- `npm --prefix frontend run lint` — pass.
- `npm --prefix frontend run typecheck` — pass.
- `npm --prefix frontend run build` — pass.
- `npm --prefix frontend test -- --run` — pass.
- `pytest -q tests/integration/test_ws_stub.py` — pass.
- `pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/integration/test_job_status_flow.py tests/integration/test_pipeline_idempotency.py tests/integration/test_pipeline_steps_happy_path.py` — pass.
- `pytest -q tests/test_health_ready.py` — pass.

## Что остается нестабильным/ограниченным
- `PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads` падает в текущем окружении (нет доступного Postgres host).
- Полный `pytest -q` не завершен в этом проходе до конца; требуется отдельный long-run в CI runner.
- `scripts/smoke.sh` не подтвержден end-to-end без поднятого backend/docker compose.
