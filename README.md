# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Quick start (Codespaces, open → run)
```bash
cp .env.example .env
make install
npm --prefix frontend ci
make cs:dev
```

Проверка:
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## Dev admin login
1. Укажите в `.env` свои значения:
   - `ADMIN_BOOTSTRAP=1`
   - `ADMIN_EMAIL=admin@example.local`
   - `ADMIN_PASSWORD=<your-password>`
   - `ADMIN_TENANT=demo`
2. Запустите `make cs:dev`.
3. В логах backend дождитесь `Admin created/exists`.
4. Откройте `http://localhost:5173/auth/login` и войдите по `tenant/email/password`.

> Секреты не хранятся в репозитории; bootstrap работает только при `APP_ENV=development|test`.

## Testing
- CLI: `make cs:test`
- Pytest discovery: `pytest --collect-only -q`
- VS Code Testing panel: Python + Vitest Explorer (см. `docs/testing.md`).

## Source of truth
- ТЗ платформы: [docs/spec/TZ.md](docs/spec/TZ.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Гайд по тестам: [docs/testing.md](docs/testing.md)
- Матрица соответствия: [docs/audit/TZ_COMPLIANCE.md](docs/audit/TZ_COMPLIANCE.md)
- Карта архитектуры: [docs/audit/ARCHITECTURE_MAP.md](docs/audit/ARCHITECTURE_MAP.md)
