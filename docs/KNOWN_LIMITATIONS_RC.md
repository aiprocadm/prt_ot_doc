# KNOWN LIMITATIONS (RC)

## Внешние интеграции и инфраструктура
- В текущем окружении не поднят доступный PostgreSQL хост для alembic-миграций (`socket.gaierror: [Errno -2] Name or service not known`).
- Полноценный smoke через `scripts/smoke.sh` требует заранее поднятого backend на `localhost:8000` и docker-compose контура.

## Backend
- Полный регрессионный `pytest -q` остается долгим и не завершен в этом цикле; возможны невыявленные дефекты вне критического набора.
- WS endpoint `/ws/v1/events` остается сознательным stub (`501` при валидном tenant), что ожидаемо до реализации real-time слоя.

## Frontend
- Базовая стабильность подтверждена (lint/typecheck/tests/build), но e2e браузерный проход фронт+бэк в этом цикле не выполнялся.

## CI/DevOps
- Для финального release sign-off обязателен полный CI-прогон в целевой среде с поднятыми зависимостями (DB, сервисный контур, smoke).
