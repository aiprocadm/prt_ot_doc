# RUNBOOK RC

## 1) Подготовка окружения
```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## 2) Backend: миграции и старт
```bash
PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3) Таргетный RC regression (задачи)
```bash
APP_ENV=test REDIS_URL=memory:// REDIS_RESULT_URL=cache+memory:// RATE_LIMIT_STORAGE_URI=memory:// \
pytest -vv tests/test_task_status.py
```

## 4) Frontend quality gates
```bash
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

## 5) Smoke минимум
```bash
bash scripts/smoke.sh
```

> Примечание: при SQLite fallback smoke может перейти в ограниченный режим из-за JSONB в миграциях; для финального RC smoke рекомендуется PostgreSQL-окружение.
