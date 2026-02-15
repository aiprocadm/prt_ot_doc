# FAILURE_MAP

## Verification log (2026-02-15)

Проверки, выполненные в рамках сценария "новичок в Codespaces":
1. `make cs:reset`
2. `cp .env.example .env`
3. Обновление `.env` с `ADMIN_BOOTSTRAP=1`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`
4. `timeout 90s make cs:dev`
5. `make cs:test`
6. `./scripts/pytest.sh --collect-only -q`
7. `npm --prefix frontend run test`

## Результаты
- Backend стартует в dockerless режиме, `/health` доступен.
- В startup-логах подтверждён dev bootstrap: `Admin created/exists: a***@example.local`.
- `make cs:test` проходит без поднятых Redis/MinIO.
- `pytest --collect-only` стабилен через `./scripts/pytest.sh`.
- Frontend vitest проходит.

## Зафиксированные риски (не блокеры)
- `timeout 90s make cs:dev` завершается кодом 124/143 из-за принудительной остановки долгоживущих dev-серверов (ожидаемо для CI-проверки).
- В тестах остаются предупреждения (`SAWarning`, React `act(...)`, router future flags), но они не ломают прохождение suite.
