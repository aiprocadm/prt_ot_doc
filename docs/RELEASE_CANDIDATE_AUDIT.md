# Release Candidate Audit (final pass)

## Контекст прохода
- Репозиторий: `prt_ot_doc`.
- Тип прохода: финальная стабилизация release-candidate (backend + frontend + CI + smoke-блоки).
- Дата: 2026-03-13.

## Что проверено

### Backend
- Проверен импорт/сборка Python-кода: `python -m compileall -q backend/app`.
- Проверен контракт OpenAPI: `PYTHONPATH=backend python scripts/contract/validate.py`.
- Проверен запуск API:
  - `healthz` возвращает `{"status":"ok"}` при локальном запуске `uvicorn`.
  - `readyz` корректно возвращает `503`, если внешние зависимости (Postgres/Redis) недоступны.

### Frontend
- Выполнен полный CI-скрипт фронтенда: `npm --prefix frontend run ci`.
- Подтверждено:
  - lint проходит;
  - typecheck проходит;
  - vitest проходит;
  - production build (`vite build`) успешен.

### CI / качество
- Проверен guard CI-скопинга запросов: `python scripts/ci/check_scoped_queries.py` (успешно).
- Подтверждена работоспособность npm/pip bootstrap для CI-окружения.

## Обнаруженные критические риски
1. `readyz` зависит от доступности Postgres/Redis и в изолированном окружении ожидаемо краснеет (503) — это корректный fail-fast, но блокирует «полностью зеленый» инфраструктурный smoke без поднятых сервисов.
2. Фронтенд-тесты проходят, но в логах много React `act(...)` warnings и future warnings от React Router — не блокируют CI, но создают шум и затрудняют triage.
3. В production-build фронтенда остаются большие чанки (предупреждение Vite >500kB).

## Что стабилизировано этим проходом
- Подтверждена стабильность `frontend` CI-пайплайна в полном режиме `npm run ci`.
- Подтверждена целостность backend-кода на уровне импорта/компиляции и OpenAPI-валидатора.
- Подтверждено корректное поведение health/readiness-контуров в условиях отсутствующих инфраструктурных зависимостей.

## Остаточные риски перед релизом
- Для финального sign-off нужен прогон smoke в окружении с поднятыми Postgres/Redis (и, при необходимости, MinIO).
- Нужна плановая очистка шумных frontend test warnings.
- Желательно провести размерную оптимизацию крупных frontend-чанков.
