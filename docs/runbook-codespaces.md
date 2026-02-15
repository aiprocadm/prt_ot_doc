# Runbook: GitHub Codespaces (dockerless-first)

## Quick start
```bash
cp .env.example .env
pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm ci && cd ..
make dev:lite
```

## Health checks
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## Tests
```bash
pytest --collect-only -q
make test:lite
cd frontend && npm run test -- --run src/__tests__/apiClient.test.ts src/__tests__/TenantGate.test.tsx src/__tests__/DocumentsPage.test.tsx src/__tests__/TasksPage.test.tsx
```

## VS Code Testing panel
- Python tests are auto-discovered via `.vscode/settings.json` + `vscode_pytest.py`.
- Frontend tests run with `vitest` from `frontend` workspace.

## If Docker is available
```bash
make dev
make test
```

## Notes
- Dockerless mode uses local storage and local process topology prepared by scripts in `scripts/`.
- Tenant header (`X-Tenant`) is mandatory for business `/api/v1/*` routes.

## Вход в админку (dev-only, без секретов в репозитории)
1. Скопируйте env-шаблон и задайте свои значения:
   ```bash
   cp .env.example .env
   # укажите собственный пароль, не коммитьте его
   export ADMIN_BOOTSTRAP=1
   export ADMIN_EMAIL=admin@example.local
   export ADMIN_PASSWORD='<your-strong-password>'
   export ADMIN_TENANT=demo
   ```
2. Запустите стек (`make dev:lite` или `make dev`). На старте API в `development/test` автоматически создаст admin-пользователя, если его нет.
3. Откройте UI (обычно `http://localhost:5173/auth/login`).
4. На форме логина введите:
   - Email: значение `ADMIN_EMAIL`
   - Password: значение `ADMIN_PASSWORD`
   - Tenant: `ADMIN_TENANT` (или выбранный tenant в UI)
5. Проверка после входа: откройте `/admin`, затем `/documents` (или Users/Organizations, если включены в меню).

> Безопасность: bootstrap работает только для `APP_ENV=development|test`; в production создание через env блокируется.
