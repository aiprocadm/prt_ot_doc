# Local Test Runbook

## Предварительные требования
- Python 3.12
- Node.js 20+
- Docker + docker compose (для smoke)

## Быстрый старт
1. `cp .env.example .env`
2. `make install`
3. `make frontend-install`

## Базовые команды
- `make test`
- `make test-backend`
- `make test-frontend`
- `make test-smoke`
- `make ci-local`

## Backend-only (быстрая диагностика)
- `pytest -q --maxfail=5`
- `pytest -q tests/integration/test_pipeline_idempotency.py::test_pipeline_runs_idempotency`
- `pytest -q tests/pdf/test_api_idempotency.py::test_convert_pdf_requires_idempotency`

## Инициализация БД/миграций
- Alembic heads: `PYTHONPATH=backend python -m alembic -c backend/app/migrations/alembic.ini heads`
- Upgrade требует рабочий `DATABASE_URL` (обычно Postgres в docker compose).

## Частые проблемы
- `.venv/bin/pytest: No such file or directory` → выполнить `make install`.
- `make test-smoke` не подключается к `localhost:8000` → сначала `docker compose up -d --build`.
- `alembic upgrade heads` падает с `socket.gaierror` → недоступен БД-хост из `DATABASE_URL`.
