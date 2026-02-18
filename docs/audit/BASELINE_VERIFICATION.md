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
Результат: backend и frontend запускаются.

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
- Backend: `285 passed, 1 skipped`.
- Frontend: `23 passed` test files, `44 passed` tests.

### 5) Pytest discovery
```bash
./scripts/pytest.sh --collect-only -q
```
Результат: успешно, обнаружены тесты в `tests/` и `integration_tests/`.

### 6) Frontend tests (direct)
```bash
npm --prefix frontend test
```
Результат: успешно (`23 passed`, `44 passed`).

## Что было исправлено
- Добавлены и обновлены документы source-of-truth:
  - `docs/spec/TZ_FULL_UNIFIED.md`
  - `docs/audit/TZ_COVERAGE_MATRIX.md`
- README и docs индекс приведены к единой точке входа для новичка.

## Повторяемость
Сценарий `make cs:reset` → `cp .env.example .env` → `make cs:dev` → `make cs:test` воспроизводим в чистом Codespace.
