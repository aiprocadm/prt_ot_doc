# FAILURE_MAP

## Verification log (2026-02-15)

Проверки, выполненные в рамках сценария "новичок в Codespaces":
1. `make cs:reset`
2. `cp .env.example .env`
3. Обновление `.env` с `ADMIN_BOOTSTRAP=1`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`
4. `make cs:dev` (проверен startup backend/frontend и прерван вручную после ready-сигналов)
5. `make cs:test`
6. `./scripts/pytest.sh --collect-only -q`

## Результаты
- Backend стартует в dockerless режиме, `/health` доступен.
- В startup-логах подтверждён dev bootstrap: `Admin created/exists: a***@example.local`.
- `make cs:test` проходит без поднятых Redis/MinIO.
- `pytest --collect-only` стабилен через `./scripts/pytest.sh`.
- Frontend vitest проходит как часть `make cs:test`.

## Зафиксированные риски (не блокеры)
- `make cs:dev` — долгоживущий процесс (ожидаемо); для проверки в CI его нужно останавливать таймаутом/сигналом.
- В тестах остаются предупреждения (`SAWarning`, React `act(...)`, router future flags), но они не ломают прохождение suite.
