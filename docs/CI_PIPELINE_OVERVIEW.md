# CI Pipeline Overview

## Stages
1. `lint-and-static` — базовые статические guard-проверки.
2. `backend-tests` — backend pytest + `backend-junit.xml` artifact.
3. `frontend-tests` — lint/typecheck/test/build фронтенда.
4. `smoke-compose` — docker-compose smoke, выгрузка логов при падении.

## Артефакты
- Backend JUnit XML: `backend-test-report`.
- Smoke logs on failure: `smoke-logs`.

## Цель
- Быстрый fail-fast по инфраструктурным/контрактным регрессиям.
- Воспроизводимость локально через `make ci-local`.
