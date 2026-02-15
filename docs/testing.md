# Testing guide

## 1) CLI (recommended)
```bash
make cs:test
```

## 2) Pytest discovery (без Redis/MinIO)
```bash
source .venv/bin/activate && pytest --collect-only -q
```

Discovery должен быть green без поднятых внешних сервисов.
Для этого используются in-memory/local defaults из `test_env_defaults.py` (через `sitecustomize.py` и `vscode_pytest.py`).

## 3) KPI regression suite (MVP KPI-1..KPI-5)
```bash
source .venv/bin/activate && pytest \
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

## 6) Если discovery пустой
1. Проверьте interpreter в VS Code: `.venv/bin/python`.
2. Выполните `make install`.
3. Запустите `source .venv/bin/activate && pytest --collect-only -q`.
4. Если всё ещё пусто — перезапустите Testing panel (Reload Window).
