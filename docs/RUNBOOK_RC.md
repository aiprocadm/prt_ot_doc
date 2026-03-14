# RUNBOOK RC

## 1) Поднять проект локально
```bash
cp .env.example .env
make cs:dev
```

Backend: `http://localhost:8000`  
Frontend: `http://localhost:5173`

## 2) Проверки backend/frontend
```bash
./scripts/codex_audit.sh
cd frontend && npm ci && npm run lint && npm run typecheck && npm run test -- --run && npm run build
```

## 3) Smoke-проход RC
```bash
# при поднятом backend
./scripts/smoke.sh
```

## 4) Целевые стабилизированные backend тесты
```bash
pytest -q tests/test_files_bus_service.py tests/test_files_core_next54.py tests/test_next29_files_service.py
pytest -q tests/test_tenancy_enforcement.py::test_missing_x_tenant_returns_400 tests/test_next23_pipelines.py::test_pipeline_run_requires_x_tenant_header
pytest -q tests/test_packs_run.py::test_pack_run_enqueue tests/test_pack_listing.py::test_pack_run_idempotency_conflict tests/test_idempotency.py::test_pack_run_idempotency
```

## 5) Что дополнительно прогнать перед релизом
```bash
pytest -q
make lint
```

Если в пп.5 остаются красные тесты/линт — свериться с `docs/KNOWN_LIMITATIONS_RC.md` и `docs/CI_STABILIZATION_REPORT.md`.
