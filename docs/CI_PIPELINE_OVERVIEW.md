# CI Pipeline Overview

## Workflow
- `.github/workflows/ci.yml`

## Jobs
1. `lint-and-static`
   - Python setup + deps
   - `python scripts/ci/check_scoped_queries.py`
2. `backend-tests`
   - Python setup + deps
   - `pytest --junitxml=artifacts/backend-junit.xml`
   - artifact: `backend-test-report`
3. `frontend-tests`
   - Node 20 + npm cache
   - `npm --prefix frontend ci`
   - `npm --prefix frontend run ci` (lint + typecheck + test + build)
4. `smoke-compose`
   - `docker compose up -d --build`
   - `make smoke`
   - logs artifact (`smoke-logs`) on failure

## Что стабилизировано
- Устранены backend-падения из-за устаревших тестовых контрактов (fixtures/DI/router wiring).
- Добавлен рабочий путь для PDF API в основном tenant-router.

## Остаточные риски
- `smoke-compose` чувствителен к инфраструктуре Docker/сервисам.
- Migration gate не вынесен отдельно в CI с гарантированным Postgres сервисом.
