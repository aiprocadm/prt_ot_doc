# План стабилизации (поэтапно)

Принципы: не ломать публичные API; сначала тесты и наблюдаемость, затем рефакторинг; атомарные PR.

## Фаза 0 — Зафиксировать поведение (1–2 спринта)

- [x] Критичные runtime-дефекты (импорт `func` в `api/v1/router.py`).
- [x] Тесты на staging-конфигурацию (`tests/test_settings_staging_hardening.py`) с изоляцией env.
- [x] Контракт `_run_coroutine` (`tests/test_tasks_run_coroutine.py`) до рефакторинга Celery/async bridge.
- [ ] Инвентаризация эндпоинтов без tenant dependency (ручной чеклист + grep по `create_public_router`).

## Фаза 1 — Конфигурация и CI gates

- [x] `CONFIGURATION_HARDENING.md`, ужесточение staging для инфраструктурных секретов.
- [ ] Постепенно включить `ruff check backend/app`: сначала исправить F821/F841/E741 в hot-path модулях, затем E402 в `db/base.py` (или явные noqa с обоснованием).
- [ ] Расширить `mypy` с `services,schemas` на `api/deps`, `middleware`, `core` — по одному пакету за PR.

## Фаза 2 — Декомпозиция God-files

- [ ] `tasks.py`: вынести группы задач в `app/tasks/` (documents, pdf, outbox, webhooks) с re-export из `tasks.py` для Celery autodiscover.
- [ ] `models/models.py`: только re-exports; новые модели — в доменных модулях (уже частично в `modules/*`).
- [ ] Крупные routes: выделить `services`/`use_cases` для телеобработчиков, оставить в route тонкий I/O.

## Фаза 3 — Reliability (jobs, outbox, webhooks)

- [ ] Документ safe rerun для каждой критичной задачи (идемпотентность по ключу / по состоянию БД).
- [ ] Единая политика retry: terminal exceptions vs transient; связь с DLQ.
- [ ] Watchdog уже в beat — проверить метрики и алерты.

## Фаза 4 — Frontend predictable enterprise UI

- [ ] Единые паттерны: `LoadingScreen` / `ErrorState` / empty (чеклист по страницам).
- [ ] Опционально: TanStack Query для новых экранов с тяжёлым server state; не мигрировать Zustand глобально в одном PR.

## Фаза 5 — E2E и регрессии

- [x] Каркас Playwright: `frontend/e2e/smoke.spec.ts`, `playwright.config.ts`, скрипты `e2e` / `e2e:install` (по умолчанию dev-сервер при `E2E_START_SERVER=1`; prod preview — `E2E_PREVIEW=1`).
- [x] Ручной workflow `.github/workflows/e2e-smoke.yml` (GitHub Actions → workflow_dispatch).
- [ ] Расширить сценарии: список документов, wizard/polling, 403 UI, logout — см. `REGRESSION_TEST_MATRIX.md`.
- [ ] Опциональный job в основном `ci.yml` после выделенного тестового стенда и секретов (`E2E_USER_*`).

## Фаза 6 — Observability

- [ ] Метрики: latency по маршрутам, глубина очереди, длительность PDF, webhooks success/fail.
- [ ] Запрет логирования сырого PII; маскирование в middleware.
