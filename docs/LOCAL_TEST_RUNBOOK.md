# Local Test Runbook

## Предварительные требования
- Python 3.12
- Node 20+
- Docker (для smoke)

## Инициализация
1. `cp .env.example .env`
2. `make install`
3. `make frontend-install`

## Команды baseline
- `make test`
- `make test-backend`
- `make test-frontend`
- `make test-smoke`
- `make ci-local`

## Особенности
- Backend тесты используют изолированную SQLite DB на каждый app fixture.
- Redis/rate limiter в тестах работают в memory-режиме.

## Частые проблемы
- Если `smoke` падает: проверить `docker compose logs --tail=200`.
- Если frontend `npm ci` падает: удалить `frontend/node_modules` и повторить.
