# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Source of truth
- ТЗ платформы: [docs/spec/TZ.md](docs/spec/TZ.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Запуск тестов: [docs/testing.md](docs/testing.md)
- Аудит соответствия ТЗ: [docs/audit/TZ_COMPLIANCE.md](docs/audit/TZ_COMPLIANCE.md)
- Карта архитектуры: [docs/audit/ARCHITECTURE_MAP.md](docs/audit/ARCHITECTURE_MAP.md)

## Quick start (Codespaces / dockerless)
```bash
cp .env.example .env
make install
cd frontend && npm ci && cd ..
make dev:lite
```

Проверка API:
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## Dev admin login (без секретов в репозитории)
1. В `.env` задайте:
   - `ADMIN_BOOTSTRAP=1`
   - `ADMIN_EMAIL=admin@example.local`
   - `ADMIN_PASSWORD=<your-password>`
   - `ADMIN_TENANT=demo`
2. Запустите `make dev:lite`.
3. Убедитесь по логам API, что есть строка `Admin created/exists`.
4. Откройте `http://localhost:5173/auth/login` и войдите с `email/password/tenant` из env.

> Bootstrap работает только в `APP_ENV=development|test`; в production создание admin через env блокируется.

## Alternative: Docker mode
```bash
cp .env.example .env
make dev
```

## CI
GitHub Actions workflow: `.github/workflows/ci.yml`.
- `backend-tests`: Python 3.12 + `pytest`
- `frontend-tests`: Node 20 + `npm run ci`
