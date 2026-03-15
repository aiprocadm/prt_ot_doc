# RUNBOOK RC

## 1) Подготовка окружения
```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## 2) Regression-срез RC (обновленный)
```bash
pytest -q \
  tests/test_documents_status_flow.py \
  tests/test_files_bus_service.py \
  tests/test_files_core_next54.py \
  tests/test_next29_files_service.py \
  tests/test_next62_analytics_search_export_center.py \
  tests/test_pack_download_api.py \
  tests/test_pipeline_profile_graph_and_api.py \
  tests/test_replace_api.py \
  tests/test_templates_pipeline_api.py \
  tests/unit/test_policy_engine.py
```

## 3) Полный backend прогон (по необходимости)
```bash
pytest -q
```

## 4) Frontend gates
```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run
npm --prefix frontend run build
```

## 5) Smoke минимум перед демонстрацией
```bash
bash scripts/smoke.sh
```
