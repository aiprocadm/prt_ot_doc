# BASELINE VERIFICATION

Дата: 2026-02-18

## Команды discovery

### 1) Reset
```bash
make cs:reset
```
Результат: успешно, очищены `dev.db`, `.local_storage`, `frontend/coverage`.

### 2) Environment
```bash
cp .env.example .env
```
Дополнительно в `.env` для dev-login:
- `ADMIN_BOOTSTRAP=1`
- `ADMIN_EMAIL=admin@example.local`
- `ADMIN_PASSWORD=ChangeMe123!`
- `ADMIN_TENANT=demo`

### 3) Dockerless run
```bash
make cs:dev
```
Результат: успешно, backend health поднят, frontend vite поднят, dev admin bootstrap выполнен.

### 4) Full test suite
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
Результат: успешно, тесты обнаружены для `tests/` и `integration_tests/`.

### 6) Frontend tests directly
```bash
npm --prefix frontend test
```
Результат: успешно (`23 passed`, `44 passed`).

## Вывод baseline
- Dockerless сценарий `open → run → login → tests` воспроизводим.
- KPI-ориентированные backend тесты (idempotency/tenant/outbox/risk/template guards/audit immutability) присутствуют и исполняются в составе `make cs:test`.
