# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Quick start (Codespaces: open → run)
1) Откройте Codespace.
2) Выполните команды:
```bash
cp .env.example .env
make install
make cs:dev
```
3) Откройте URL:
- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`

`make cs:dev` уже выполняет `npm ci` и поднимает backend+frontend.

## Dev login (без секретов в git)
В `.env` задайте только локальные dev-значения:
```env
ADMIN_BOOTSTRAP=1
ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=ChangeMe123!
ADMIN_TENANT=demo
```

Далее:
1. Запустите `make cs:dev`.
2. В логах backend дождитесь `Admin created/exists: ...`.
3. Откройте `http://localhost:5173/auth/login` и войдите как `tenant/email/password`.

> Bootstrap админа работает только при `APP_ENV=development|test`.

## Tests
Используйте только эти команды:
```bash
make cs:test
make test
./scripts/pytest.sh --collect-only -q
```

Не запускайте `pytest` напрямую из системного Python: без `.venv` возможны ошибки вида `ModuleNotFoundError: pytest_asyncio`.

## Source of truth
- ТЗ платформы: [docs/spec/TZ.md](docs/spec/TZ.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Гайд по тестам: [docs/testing.md](docs/testing.md)
- Матрица соответствия: [docs/audit/TZ_COMPLIANCE.md](docs/audit/TZ_COMPLIANCE.md)
- Карта архитектуры: [docs/audit/ARCHITECTURE_MAP.md](docs/audit/ARCHITECTURE_MAP.md)
