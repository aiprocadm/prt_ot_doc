# BASELINE VERIFICATION

Дата: 2026-02-18

## Команды baseline (dockerless / Codespaces)

### 1) Reset
```bash
make cs:reset
```
Результат: успешно, очищены `dev.db`, `.local_storage`, `frontend/coverage`.

### 2) Environment
```bash
cp .env.example .env
```
Для dev-login в `.env`:
- `ADMIN_BOOTSTRAP=1`
- `ADMIN_EMAIL=<ваш локальный email>`
- `ADMIN_PASSWORD=<ваш локальный пароль>`
- `ADMIN_TENANT=<tenant>`

### 3) Startup (fail-first)
```bash
make cs:dev
```
Результат: backend и frontend запускаются (`http://localhost:8000`, `http://localhost:5173`).

Наблюдения (не блокеры):
- предупреждение про отсутствие `soffice` (LibreOffice) в локальном окружении;
- предупреждение про недоступную locale `ru-RU`;
- SQLAlchemy relationship overlap warnings;
- npm предупреждения по deprecated пакетам.

### 4) Full tests
```bash
make cs:test
```
Результат: успешно.
- Backend + integration: `287 passed, 1 skipped`.
- Frontend: `23 passed` test files, `44 passed` tests.

### 5) Pytest discovery
```bash
. .venv/bin/activate && pytest --collect-only
```
Результат: успешно, обнаружено `288` тестов в `tests/` и `integration_tests/`.

### 6) Frontend tests (direct)
```bash
npm --prefix frontend test
```
Результат: успешно (`23 passed`, `44 passed`).

## Что сломалось и как починили
Критичных падений baseline не выявлено.

Найдены предупреждения среды:
- `soffice` не установлен в контейнере (PDF fallback активируется согласно dev-контракту);
- отсутствует locale `ru-RU`;
- предупреждения React testing (`act(...)`) и React Router future flags.

Это не блокирует запуск/тесты в текущем MVP, но зафиксировано как техдолг для стабилизации CI/dev UX.

## Повторяемость
Сценарий `make cs:reset` → `cp .env.example .env` → `make cs:dev` → `make cs:test` воспроизводим в чистом Codespace.
