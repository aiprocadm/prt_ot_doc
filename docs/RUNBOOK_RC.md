# RUNBOOK RC

## 1) Поднять окружение
```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## 2) Backend critical regression gate
```bash
pytest -q tests/test_tenancy_enforcement.py tests/test_idempotency.py tests/test_jobs_api.py tests/integration/test_pipeline_idempotency.py
```

## 3) Frontend CI gate
```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

## 4) Smoke gate
```bash
bash scripts/smoke.sh
```

> Примечание: в dockerless/SQLite режиме допускается fallback smoke при известной несовместимости миграций `JSONB`.

## 5) Локальная RC проверка перед демонстрацией
```bash
pytest -q tests/test_tenancy_enforcement.py tests/test_idempotency.py tests/test_jobs_api.py
npm --prefix frontend run build
bash scripts/smoke.sh
```
