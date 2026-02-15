# prt-ot-doc

Платформа управления документами и процессами ОТ/ПБ/ПромБез: FastAPI backend, React/Vite frontend, dockerless-режим для Codespaces и docker-compose для полного локального контура.

## Quick start (Codespaces: open → run)
1) Откройте Codespace.
2) Выполните 3 команды:
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
В `.env` задайте локальные значения:
```env
ADMIN_BOOTSTRAP=1
ADMIN_EMAIL=admin@example.local
ADMIN_PASSWORD=<set-your-own-password>
ADMIN_TENANT=demo
```

Далее:
1. Запустите `make cs:dev`.
2. В логах backend дождитесь `Admin created/exists`.
3. Откройте `http://localhost:5173/auth/login` и войдите как `tenant/email/password`.

> Bootstrap админа работает только при `APP_ENV=development|test`.

## Tests
```bash
make cs:test
source .venv/bin/activate && pytest --collect-only -q
```

## Dependency policy (single source of truth)
- Основной workflow: `pip` + `requirements.txt` + `requirements-dev.txt`.
- `pyproject.toml` используется только для конфигов инструментов (`pytest`, `ruff`, `black`, `mypy`).
- Poetry workflow удалён из onboarding-пути для новичка.

## Source of truth
- ТЗ платформы: [docs/spec/TZ.md](docs/spec/TZ.md)
- Runbook для Codespaces: [docs/runbook-codespaces.md](docs/runbook-codespaces.md)
- Гайд по тестам: [docs/testing.md](docs/testing.md)
- Матрица соответствия: [docs/audit/TZ_COMPLIANCE.md](docs/audit/TZ_COMPLIANCE.md)
- Карта архитектуры: [docs/audit/ARCHITECTURE_MAP.md](docs/audit/ARCHITECTURE_MAP.md)
