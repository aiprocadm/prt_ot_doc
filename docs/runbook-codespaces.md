# Runbook: GitHub Codespaces (dockerless-first)

## 1) Open → install → run
```bash
cp .env.example .env
make install
npm --prefix frontend ci
make cs:dev
```

`make cs:dev` (alias `make dev:lite`) включает dockerless-профиль:
- SQLite (`dev.db`)
- local storage (`.local_storage/`)
- eager tasks (`CELERY_EAGER=true`)
- in-memory rate limit storage (`RATE_LIMIT_STORAGE_URI=memory://`)

## 2) Проверка что всё поднялось
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

## 3) Вход в админку (dev)
1. В `.env` задайте:
   ```env
   ADMIN_BOOTSTRAP=1
   ADMIN_EMAIL=admin@example.local
   ADMIN_PASSWORD=<your-password>
   ADMIN_TENANT=demo
   ```
2. Выполните `make cs:dev`.
3. В логах backend должна быть строка `Admin created/exists`.
4. Откройте `http://localhost:5173/auth/login`.
5. Введите `tenant/email/password` из `.env`.

Если вход не проходит:
- проверьте что `APP_ENV=development` или `test`;
- проверьте что `ADMIN_PASSWORD` не пустой;
- удалите локальное состояние: `make cs:reset` и запустите `make cs:dev` снова.

## 4) Тесты
```bash
pytest --collect-only -q
make cs:test
```

## 5) VS Code Testing panel
- Python discovery: `tests/` + `integration_tests/`.
- Frontend discovery: Vitest Explorer + `npm run test`.

## 6) Сброс локального состояния
```bash
make cs:reset
```
Удаляются `dev.db`, `.local_storage/`, `frontend/coverage`.
