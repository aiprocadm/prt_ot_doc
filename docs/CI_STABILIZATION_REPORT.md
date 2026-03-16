# CI STABILIZATION REPORT (RC)

## Наблюдения по пайплайнам

### 1) Интегральный RC-гейт
- Команда: `./scripts/final_acceptance.sh`.
- Результат: `overall_status = pass`.
- Прошедшие этапы:
  - critical backend tests
  - critical frontend checks
  - e2e final regression subset
  - openapi drift
  - migrations heads
  - health and readiness
  - sample render/pdf/export flow
  - schema consistency

### 2) Локальный полный CI
- Команда: `make ci-local`.
- Результат: fail на этапе lint.
- Первопричина: массовый исторический lint-долг (`ruff`: сотни ошибок в backend/tests/scripts), а не единичная регрессия текущего RC-прохода.

### 3) Smoke
- Команда: `./scripts/smoke.sh`.
- Результат: pass в fallback-режиме.
- Деталь: в SQLite full-migration падает на JSONB (ожидаемое ограничение), затем выполняется fallback smoke и завершается успешно.

### 4) Frontend production build
- Команда: `cd frontend && npm run build`.
- Результат: pass.
- Замечание: предупреждение по размеру чанков (не блокер RC).

## Что стабилизировано
- Критические release-критерии закрыты и автоматизированно подтверждены через `final_acceptance`.
- Контрактный слой FE/BE валидирован через openapi drift checks.
- Smoke-ворота стабильны в документированном fallback-сценарии.

## Что остается нестабильным
- Lint-stage полного CI остается нестабильным из-за legacy-объема нарушений.

## План до полного «зеленого» CI
1. Выделить отдельный backlog на поэтапное устранение `ruff`-нарушений по пакетам/директориям.
2. Закрепить `final_acceptance` как обязательный pre-release gate.
3. Выполнять финальный sign-off на PostgreSQL-окружении (без SQLite fallback-ограничений).
