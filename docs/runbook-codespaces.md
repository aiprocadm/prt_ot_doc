# Runbook: GitHub Codespaces (dockerless-first)

## 1) Open → install → run
```bash
cp .env.example .env
make install
make cs:dev
```

Ожидаемый вывод `make cs:dev`:
- `Dockerless mode enabled`
- `Backend ready: http://127.0.0.1:8000/health`
- URL backend/frontend

## 2) Проверка готовности
```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

## 3) Логин в dev
1. В `.env` задайте `ADMIN_BOOTSTRAP=1`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`.
2. Запустите `make cs:dev`.
3. Проверьте лог `Admin created/exists`.
4. Откройте `http://localhost:5173/auth/login` и введите `tenant/email/password`.

## 4) KEEP_DB для повторных запусков
По умолчанию `scripts/dev_lite.sh` сбрасывает `dev.db` для чистого старта.

Чтобы сохранить данные между перезапусками:
```bash
KEEP_DB=1 make cs:dev
```

## 5) Тесты
```bash
make cs:test
source .venv/bin/activate && pytest --collect-only -q
```

## 6) FAQ
- **Порт не открывается:** проверьте, что backend отвечает по `/health`, затем откройте forwarded port 5173.
- **Не могу войти:** проверьте `ADMIN_PASSWORD` (не `__SET_ME__`) и `APP_ENV=development|test`.
- **tenant_required (400):** для `/api/v1/*` укажите `X-Tenant`; в UI сначала выберите tenant.
- **node_modules ошибки:** выполните `make cs:dev` повторно (скрипт сам делает `npm ci`) или отдельно `npm --prefix frontend ci`.

## 7) Reset
```bash
make cs:reset
```
Удаляются `dev.db`, `.local_storage/`, `frontend/coverage`.
