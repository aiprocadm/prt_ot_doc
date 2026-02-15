# Testing guide

## 1) CLI (recommended)
```bash
make cs:test
```

## 2) Pytest без сюрпризов
```bash
./scripts/pytest.sh --collect-only -q
./scripts/pytest.sh tests/test_idempotency.py -q
```

`./scripts/pytest.sh` гарантирует запуск внутри `.venv` и автоматически ставит зависимости при первом запуске.

> Не запускайте `pytest` напрямую из системного Python. В Codespaces это часто приводит к `ModuleNotFoundError` (например, `pytest_asyncio`).

## 3) KPI regression suite (MVP KPI-1..KPI-5)
```bash
./scripts/pytest.sh \
  tests/test_idempotency.py \
  tests/test_tenant_header_required.py \
  tests/test_template_delete.py \
  tests/test_outbox_dispatch.py \
  tests/test_risk_assessment_kpi5.py
```

## 4) Frontend
```bash
npm --prefix frontend run test
```

## 5) VS Code Testing panel
- Python:
  - Interpreter: `${workspaceFolder}/.venv/bin/python`
  - Discovery folders: `tests`, `integration_tests`
- Frontend:
  - Vitest Explorer
  - tests from `frontend/src/**`

## 6) Почему discovery стабильный без Redis/MinIO
- `tests/conftest.py` задаёт безопасные дефолты (`memory://`, `cache+memory://`, local storage endpoint).
- `test_env_defaults.py` — единый источник test-defaults для discovery.
- `sitecustomize.py` применяет defaults максимально рано и добавляет workspace-совместимые shim'ы.
- `vscode_pytest.py` использует тот же `apply_test_env_defaults()` внутри VS Code Testing.

Итог: discovery/pytest не требуют Redis/MinIO по умолчанию.
