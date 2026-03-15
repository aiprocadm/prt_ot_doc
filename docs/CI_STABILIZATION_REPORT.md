# CI STABILIZATION REPORT (RC)

## Что было нестабильно
- Падал критичный backend тест tenancy-isolation: контракт префикса storage key (`tenant/...` vs `tenants/...`).
- Smoke migration path в SQLite по-прежнему уязвим к PostgreSQL-специфике ревизий (`JSONB`).
- Frontend test run содержит большое количество предупреждений `act(...)` (шум в CI-логах).

## Что исправлено
1. Исправлен контракт в `backend/app/modules/files/storage.py`: текущий tenant prefix приведен к `tenants`.
2. Перепроверен backend critical regression-срез после фикса: tenancy/idempotency/jobs/pipeline-idempotency.
3. Перепроверены frontend ворота CI:
   - `npm --prefix frontend run lint`
   - `npm --prefix frontend run typecheck`
   - `npm --prefix frontend test -- --run`
   - `npm --prefix frontend run build`
4. Переподтвержден `bash scripts/smoke.sh` в dockerless fallback-режиме.

## Что стабильно в текущем прогоне
- Backend critical tests: green.
- Frontend lint/typecheck/test/build: green.
- Smoke gate: green (fallback mode для known SQLite limitation).

## Что остается нестабильным
- Полный `alembic upgrade` в SQLite-контуре для всех ревизий (из-за исторических `JSONB` миграций).
- Полный e2e/интеграционный прогон на внешних сервисах.
- Шум предупреждений `act(...)` в frontend тестах (не fail, но требует cleanup).
