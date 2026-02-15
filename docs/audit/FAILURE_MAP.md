# FAILURE_MAP

## Audit run timestamp
- 2026-02-15

## Executed "newcomer" flow
1. `cp .env.example .env`
2. `make install`
3. `npm --prefix frontend ci`
4. `pytest --collect-only -q`
5. `make cs:test`

## Failures / warnings found

### P0 (fixed in this pass)
1. `pytest --collect-only -q` падал в чистом окружении из-за попытки подключения к `redis://redis:6379` при инициализации rate limit storage.
   - **Fix:** default `RATE_LIMIT_STORAGE_URI` in `.env.example` changed to `memory://` (dockerless-safe).

2. Makefile был фактически poetry-centric (`poetry run ...`), при том что CI/devcontainer используют pip requirements.
   - **Fix:** Makefile переведён на `.venv/bin/*` pip workflow + добавлены команды `cs:dev`, `cs:test`, `cs:reset`.

### P1 (non-blocking)
- `npm ci` выводит deprecation/security warnings для транзитивных frontend зависимостей.
- `make cs:test` и `make cs:dev` выполняют повторную установку зависимостей в lite-скриптах, что замедляет cold start.

## Validation outcome
- Health endpoints `/health` и `/ready` доступны в dockerless режиме.
- Pytest discovery проходит без внешнего Redis.
- Frontend tests выполняются через `npm --prefix frontend run test`.
