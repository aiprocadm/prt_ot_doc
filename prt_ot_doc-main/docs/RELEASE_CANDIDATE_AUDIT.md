# RELEASE CANDIDATE AUDIT

Дата прохода: 2026-03-15.

## Что обнаружено в финальном аудите
- Скрипт интегральной проверки `./scripts/codex_audit.sh` проходит по целевым блокам (tenant isolation, idempotency, template/pipeline safety, webhook/outbox, backend module smoke).
- Локальный полный CI-гейт `make ci-local` остается красным из-за масштабного исторического хвоста lint-проблем (`ruff` показывает сотни нарушений по backend/tests/scripts).
- Smoke-сценарий `./scripts/smoke.sh` в SQLite-окружении корректно уходит в fallback-режим: full migration не проходит из-за JSONB в initial migration, после чего выполняется ограниченный smoke-набор и завершается успешно.
- Набор финальных приемочных проверок `./scripts/final_acceptance.sh` проходит полностью (backend critical tests, frontend checks, e2e subset, openapi drift, migrations heads, health/readiness, package/pdf flow, schema consistency).

## Что стабилизировано в этом проходе
- Подтверждена стабильность критического регрессионного набора для релиз-кандидата через `final_acceptance`.
- Подтверждена работоспособность production-сборки frontend (`npm run build`) и прохождение frontend test-gate в составе `final_acceptance`.
- Подтверждена работоспособность smoke-gate в поддерживаемом fallback-сценарии для dev SQLite.

## Что исправлено
- В рамках этого прохода изменений в код backend/frontend не вносилось; фокус — на верификации RC-состояния и фиксации ограничений.

## Оставшиеся риски
- Полный lint-контур репозитория не стабилизирован (критично для «полностью зеленого» CI).
- SQLite не является полноценной заменой PostgreSQL для миграционного smoke из-за JSONB-типов.
- Для финального sign-off требуется прогон полного CI на целевом окружении (PostgreSQL + полная матрица pipeline).
