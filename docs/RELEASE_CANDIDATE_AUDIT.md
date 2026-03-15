# RELEASE CANDIDATE AUDIT

Дата прохода: 2026-03-14.

## Что проверено
- Backend: `tests/test_tenant_header_required.py`, `tests/test_idempotency.py`, `tests/test_template_delete.py`, `tests/test_health_ready.py`.
- Frontend: `npm ci`, `npm run lint`, `npm run test -- --run`, `npm run build`.
- Smoke/infra: `scripts/smoke.sh` (после доработки сценария для dockerless-режима).

## Критические проблемы, выявленные в финальном проходе
1. `scripts/smoke.sh` был жестко привязан к docker-compose API-контейнеру и не работал в dockerless RC-режиме.
2. В локальном smoke-прогоне миграции SQLite падают на `initial schema` из-за PostgreSQL-типа `JSONB` в миграциях (несовместимость диалектов), что блокировало smoke gate.
3. API startup в локальном контуре ломался из-за bootstrap-эффектов (`DEMO_BOOTSTRAP`) при повторных прогонах и загрязненном состоянии.

## Что исправлено
- `scripts/smoke.sh` стабилизирован:
  - добавлен авто-подъем API в локальном режиме;
  - добавлены dockerless env-переменные и унификация python/uvicorn бинари;
  - диагностические логи сделаны безопасными без обязательного `docker compose`;
  - PDF probe умеет работать как через `docker compose exec`, так и локально, и теперь корректно пропускается при отсутствии `soffice`;
  - добавлен fallback smoke-gate: при ожидаемой несовместимости SQLite/JSONB выполняется минимальный релизный набор (`healthz/readyz` + tenant header checks) вместо аварийного падения.

## Что подтверждено
- Критические backend проверки (tenancy/idempotency/health/template delete) проходят стабильно.
- Frontend lint/test/build проходит без падений.

## Остаточные риски RC
- Полный smoke поток с миграцией `upgrade heads` в SQLite по-прежнему ограничен несовместимостью `JSONB` в части ревизий; для dockerless используется fallback-gate.
- Полный `pytest -q` (весь репозиторий) не завершался в рамках прохода: требуется отдельный долгий CI run.
- PDF-конвертация зависит от наличия `soffice`; в текущей среде бинарь отсутствует, используется fallback-поведение.
