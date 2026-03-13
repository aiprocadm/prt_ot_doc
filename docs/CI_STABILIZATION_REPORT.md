# CI Stabilization Report (RC final)

## Что было проверено в этом проходе
- `python scripts/ci/check_scoped_queries.py`.
- `npm --prefix frontend ci`.
- `npm --prefix frontend run ci` (lint + typecheck + test + build).
- `python -m compileall -q backend/app`.
- `PYTHONPATH=backend python scripts/contract/validate.py`.

## Итог по стадиям

### Стабильно (green)
1. **Frontend CI stage**: полностью проходит (`lint`, `typecheck`, `vitest`, `vite build`).
2. **Scoped query guard**: проходит.
3. **Backend compile/import sanity**: проходит (`compileall`).
4. **OpenAPI contract sanity**: проходит (`scripts/contract/validate.py`).

### Условно стабильно / зависит от окружения
1. **`/readyz`**: корректно возвращает `503`, если не подняты Postgres/Redis.
2. **Инфраструктурный smoke с миграциями и джобами**: требует запущенные внешние сервисы (как минимум Postgres/Redis).

## Основные наблюдения по качеству
- Во frontend тестах есть большой объем `act(...)` warnings и router future warnings. Они не валят pipeline, но ухудшают сигнал в CI-логах.
- В production build остаются предупреждения Vite по размеру чанков.

## Что осталось для полного «release green»
1. Прогнать backend smoke/интеграцию в окружении с Postgres/Redis/MinIO.
2. Отдельно зафиксировать результаты tenant/idempotency/job-state smoke в едином артефакте.
3. Снизить шум frontend test warnings (приоритизация по наиболее часто повторяющимся тестам).
