# RUNBOOK RC

## 1. Подготовка окружения
```bash
cp .env.example .env
npm --prefix frontend ci
```

## 2. Базовая RC-валидация (локально)
```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend test -- --run

pytest -q tests/integration/test_ws_stub.py
pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/integration/test_job_status_flow.py tests/integration/test_pipeline_idempotency.py tests/integration/test_pipeline_steps_happy_path.py
pytest -q tests/test_health_ready.py
```

## 3. Миграции
```bash
PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads
```
Если команда падает с ошибкой резолвинга host, проверьте доступность PostgreSQL и переменные окружения БД.

## 4. Smoke
```bash
# backend должен быть запущен и слушать localhost:8000
./scripts/smoke.sh
```

## 5. Финальный release gate
1. Прогнать полный `pytest -q` в CI runner.
2. Прогнать smoke в окружении с реальными зависимостями.
3. Проверить acceptance checklist и known limitations перед sign-off.
