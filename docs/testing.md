# Testing guide

## Backend suites

### Discovery (CLI + VS Code)
```bash
pytest --collect-only -q
```
Pytest discovery включает оба каталога:
- `tests/`
- `integration_tests/`

### Full backend
```bash
pytest
```

### Dockerless regression suite
```bash
make test:lite
```

### KPI-focused checks
```bash
pytest tests/test_idempotency.py tests/test_tenant_header_required.py tests/test_template_delete.py tests/test_risk_assessment_kpi5.py
```

## Frontend suites
```bash
cd frontend
npm ci
npm run test
```

CI-команда фронтенда:
```bash
npm run ci
```

## All tests (manual)
```bash
pytest
cd frontend && npm run test
```
