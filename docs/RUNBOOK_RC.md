# RUNBOOK RC

## 1) Подготовка окружения
```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## 2) Базовый backend запуск
```bash
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 3) Миграции
```bash
PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads
```

> Примечание: для SQLite часть миграций с JSONB не совместима; для локального RC-smoke используйте fallback-режим `scripts/smoke.sh` или PostgreSQL-окружение.

## 4) RC-аудит и приемка
```bash
./scripts/codex_audit.sh
./scripts/final_acceptance.sh
cat artifacts/final_acceptance/summary.json
```

## 5) Smoke
```bash
./scripts/smoke.sh
```

## 6) Frontend проверки
```bash
cd frontend && npm run test
cd frontend && npm run build
```

## 7) Полный локальный CI (ожидаемое ограничение: lint debt)
```bash
make ci-local
```
