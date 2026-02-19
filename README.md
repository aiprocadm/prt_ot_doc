# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Quick start (Codespaces)
```bash
make cs:reset
cp .env.example .env
# в .env задайте ADMIN_BOOTSTRAP=1, DEMO_BOOTSTRAP=1 и ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_TENANT
make cs:dev
make cs:test
```

После старта:
- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`
- Ready probe: `http://localhost:8000/readyz`

## Dev login (без секретов в git)
Используйте значения **из локального `.env`**:
```env
ADMIN_BOOTSTRAP=1
ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=ChangeMe123!
ADMIN_TENANT=demo
```

Bootstrap админа активен только для `APP_ENV=development|test`.

## Tests
```bash
make cs:test
./scripts/pytest.sh --collect-only -q
npm --prefix frontend test
```

## Source of truth
- Единое полное ТЗ: [docs/spec/TZ_FULL_UNIFIED.md](docs/spec/TZ_FULL_UNIFIED.md)
- Матрица покрытия ТЗ: [docs/audit/TZ_COVERAGE_MATRIX.md](docs/audit/TZ_COVERAGE_MATRIX.md)
- Baseline verification: [docs/audit/BASELINE_VERIFICATION.md](docs/audit/BASELINE_VERIFICATION.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Demo walkthrough: [docs/runbook/DEMO_WALKTHROUGH.md](docs/runbook/DEMO_WALKTHROUGH.md)
- Гайд по тестам: [docs/testing.md](docs/testing.md)
