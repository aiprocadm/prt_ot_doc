# Testing guide

## Быстрый путь для Codespaces
```bash
make cs:test
```

## Backend

### Discovery (CLI + VS Code)
```bash
pytest --collect-only -q
```

Pytest discovery включает:
- `tests/`
- `integration_tests/`

### Полный backend suite
```bash
pytest
```

### KPI regression (KPI-1..KPI-5)
```bash
pytest tests/test_idempotency.py tests/test_tenant_header_required.py tests/test_template_delete.py tests/test_outbox_dispatch.py tests/test_risk_assessment_kpi5.py
```

## Frontend
```bash
npm --prefix frontend run test
```

## VS Code Testing panel
- Python: включён `pytest`, аргументы discovery `tests integration_tests`.
- Frontend: расширение Vitest Explorer обнаруживает тесты из `frontend/src/**`.
