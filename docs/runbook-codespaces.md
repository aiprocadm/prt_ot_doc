# Runbook: GitHub Codespaces (dockerless-first)

## 1) Open → install → run
```bash
cp .env.example .env
make install
cd frontend && npm ci && cd ..
make dev:lite
```

`make dev:lite` включает dockerless-профиль:
- `APP_RUN_MODE=dockerless`
- SQLite (`dev.db`)
- local storage (`.local_storage/`)
- eager tasks (`CELERY_EAGER=true`)

## 2) Проверка, что backend/frontend поднялись
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## 3) Dev admin login (без хранения секретов)
1. В `.env` задайте собственные значения:
   ```env
   ADMIN_BOOTSTRAP=1
   ADMIN_EMAIL=admin@example.local
   ADMIN_PASSWORD=<your-password>
   ADMIN_TENANT=demo
   ```
2. Запустите `make dev:lite`.
3. В логах API проверьте сообщение `Admin created/exists: ...`.
4. Откройте `http://localhost:5173/auth/login`.
5. Введите `email/password/tenant` из env.

Если `ADMIN_PASSWORD` пустой, bootstrap будет пропущен с предупреждением `admin.bootstrap.skipped`.

## 4) Тесты
```bash
pytest --collect-only -q
make test:lite
cd frontend && npm run test
```

## 5) VS Code Testing panel
- Python: `python.testing.pytestArgs = ["tests", "integration_tests"]`.
- Frontend: Vitest Explorer extension + `npm run test`.

## 6) Docker mode (optional)
Если в окружении доступен Docker daemon:
```bash
make dev
make test
```
