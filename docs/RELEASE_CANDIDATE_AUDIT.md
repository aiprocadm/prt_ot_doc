# RELEASE CANDIDATE AUDIT

Дата прохода: 2026-03-15.

## Что проверено
- **Backend critical suite**: tenancy, idempotency, jobs API, pipeline idempotency.
- **Frontend quality gates**: lint, typecheck, unit/integration tests (vitest), production build.
- **Smoke gate**: `scripts/smoke.sh` в dockerless fallback-режиме с проверками health/tenant enforcement.

## Критические проблемы, выявленные в финальном проходе
1. Контракт tenant-storage key в файловом модуле был рассогласован: код строил префикс `tenant/...`, а тесты и остальной код ожидали `tenants/...`.
2. Полный migration smoke в SQLite остается ограничен ревизиями с PostgreSQL-типами (`JSONB`) — это не регрессия текущего цикла, но блокирует полноценный `upgrade` smoke в dockerless.
3. Frontend тесты проходят, но в логах остаются многочисленные React `act(...)` warnings (нестабильность UX-тестов не приводит к падению, но требует отдельного техдолг-прохода).

## Что исправлено
- Исправлен ключевой backend дефект контракта в storage-ключах для tenancy isolation: текущий префикс переведен на `tenants/...`, что выровняло код с тестами/контрактом и устранило падение критичного tenancy-теста.
- Повторно подтверждена стабильность smoke fallback gate и frontend/CI базовых ворот.

## Что подтверждено в этом проходе
- Проходят: `tests/test_tenancy_enforcement.py`, `tests/test_idempotency.py`, `tests/test_jobs_api.py`, `tests/integration/test_pipeline_idempotency.py`.
- Проходят: `npm --prefix frontend run lint`, `typecheck`, `test -- --run`, `build`.
- Проходит: `bash scripts/smoke.sh` (ожидаемый fallback при SQLite/JSONB несовместимости).

## Остаточные риски RC
- Полный `alembic upgrade` в SQLite-контуре остается ограничен несовместимостью диалектов для части исторических ревизий.
- Часть acceptance сценариев требует полноценного Postgres+infra стенда (внешние интеграции и полный e2e).
- Frontend тестовые предупреждения `act(...)` не блокируют CI, но повышают шум и могут маскировать реальные race-condition регрессии.
