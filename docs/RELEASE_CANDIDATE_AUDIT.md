# RELEASE CANDIDATE AUDIT

Дата прохода: 2026-03-14.

## Объем аудита
- Backend: целевые интеграционные/контрактные проверки tenancy, idempotency, job pipeline, health/ready.
- Frontend: `lint`, `typecheck`, production build, unit/integration tests (Vitest).
- CI-подобный прогон: частичный `pytest -q -x` + целевые backend-смоук наборы.

## Обнаруженные критические проблемы
1. Интеграционный тест websocket-stub (`tests/integration/test_ws_stub.py`) ожидал `501` без `X-Tenant`, что конфликтовало с глобальным tenancy-правилом (`400` без tenant для бизнес-маршрутов).
2. Миграции в текущей среде не выполняются из-за отсутствующего хоста PostgreSQL (ошибка разрешения имени) и неготовой внешней инфраструктуры.
3. `scripts/smoke.sh` требует предварительно поднятого backend на `localhost:8000` и docker-compose API-контур; в текущем прогоне не выполнялся end-to-end.

## Что исправлено
- Исправлен контрактный интеграционный тест websocket-stub:
  - теперь фиксируется корректный `400` без `X-Tenant`;
  - и `501` при наличии `X-Tenant` для deferred WS-эндпойнта.

## Что подтверждено в этом проходе
- Backend ключевые проверки: tenancy/idempotency/job flow/pipeline/health — проходят.
- Frontend: lint/typecheck/build/test проходят.

## Оставшиеся риски RC
- Полный `pytest -q` не завершен в рамках окна аудита (длинный прогон); остается риск в неохваченных пакетах.
- Полный e2e smoke (`scripts/smoke.sh`) не подтвержден в этой среде из-за отсутствия поднятого dockerized API и infra-зависимостей.
- Миграции Postgres требуют доступной БД из окружения (локально не резолвится хост).
