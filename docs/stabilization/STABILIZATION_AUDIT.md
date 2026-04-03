# Стабилизация платформы — технический аудит (фактический код)

Дата обновления: 2026-04-03. Метод: чтение исходников, grep по опасным паттернам, обзор `tests/` и CI.

## Executive summary

| Зона | Оценка | Комментарий |
|------|--------|-------------|
| Tenant HTTP boundary | Хорошо | `X-Tenant` обязателен; mismatch с JWT → `403` / `TENANT_SCOPE_MISMATCH` |
| Tenant в фоне | Требует ревью | Задачи принимают `tenant_slug`; нужен аудит всех entrypoints Celery |
| Async/sync bridges | **High risk** | `tasks._run_coroutine`, `db/session.py`, `runtime_bootstrap._run_coro_sync` |
| God-files | **Maintainability** | `tasks.py`, `models.py`, `api/v1/router.py`, крупные routes |
| Static analysis | Слабый gate | mypy только `services`+`schemas`; ruff на весь пакет — большой бэклог |
| Integration / E2E | Разреженно | Мало `integration_tests/`; Playwright smoke добавлен (`frontend/e2e/`), отдельный workflow `e2e-smoke.yml` (ручной запуск) |

**Недавние артефакты стабилизации (код):** контрактные тесты `tests/test_tasks_run_coroutine.py`; исправление `tsc` в `searchPageStates.test.tsx` (раньше ломал `npm run build`); Playwright по умолчанию на **dev-сервере** при `E2E_START_SERVER=1` из‑за взаимодействия prod+PWA и `serviceWorkers: block`.

---

## Таблица проблем (severity / влияние / файлы / почему опасно / как чинить без регрессии)

### B1 — `tasks._run_coroutine`: `asyncio.run` + `threading.Thread`

- **Severity:** high  
- **Влияние:** runtime, observability, deadlock risk (редко)  
- **Файлы:** `backend/app/tasks.py` (~L102–122)  
- **Почему опасно:** При уже запущенном event loop Celery/тест создаётся **daemon**-поток с **отдельным** `asyncio.run`. Сложно дебажить, возможны edge cases с TLS/contextvars и закрытием loop.  
- **Как чинить:** (1) Зафиксировать контракт тестами. (2) Для worker — поэтапно переводить entrypoints на **нативный async** (`celery` с pool async или отдельный async worker process). (3) До миграции — явное structured logging при входе/выходе `_run_coroutine`, документировать «только из sync Celery task».

### B2 — `db/session.py`: `Thread` + `asyncio.run`

- **Severity:** high  
- **Влияние:** runtime, data integrity (schema ops)  
- **Файлы:** `backend/app/db/session.py` (~L224, L287, L317, L482)  
- **Почему опасно:** Те же анти-паттерны на пути создания/удаления схем и dispose engine.  
- **Как чинить:** Выделить sync-only CLI/миграции vs async API; убрать `asyncio.run` из горячего пути запросов (убедиться, что не вызывается при обычном API).

### B3 — `runtime_bootstrap._run_coro_sync`

- **Severity:** medium–high  
- **Влияние:** startup reliability  
- **Файлы:** `backend/app/core/runtime_bootstrap.py`  
- **Почему опасно:** Дублирует логику с `tasks._run_coroutine`.  
- **Как чинить:** Единый утилитный слой с явным контрактом «вызывать только до старта loop»; тесты на dockerless SQLite bootstrap.

### B4 — Giant files

- **Severity:** medium (накопление → high)  
- **Влияние:** maintainability, testability, регрессии при ревью  
- **Файлы:**  
  - `backend/app/models/models.py` (~2.2k+ строк)  
  - `backend/app/tasks.py` (~1.7k+ строк)  
  - `backend/app/api/v1/router.py`  
  - `backend/app/api/routes/risk.py`, `documents.py`, …  
  - `backend/app/services/pipeline.py`  
- **Почему опасно:** Смешение ответственности, сложно изолировать изменения.  
- **Как чинить:** Вынос в пакеты с **re-export** и сохранением имён задач/роутов; сначала тесты на публичное поведение, потом move.

### B5 — Broad `except` в критических зонах

- **Severity:** medium  
- **Влияние:** observability, data consistency (тихие сбои)  
- **Файлы:** поиск `except Exception` в `tasks.py`, `pipeline.py`, webhooks  
- **Почему опасно:** Потеря причины сбоя, повторные неидемпотентные side effects.  
- **Как чинить:** Сужение типов, обязательный `logger.exception` + correlation/tenant; terminal vs transient классы исключений.

### B6 — Tenant isolation за пределами HTTP

- **Severity:** high (если найдётся дыра)  
- **Влияние:** security, tenancy  
- **Файлы:** `tasks.py`, `services/outbox.py`, export/webhook handlers, `pipeline`  
- **Почему опасно:** Один неверный `tenant_id` в запросе — cross-tenant утечка.  
- **Как чинить:** Интеграционные тесты «два tenant + job»; статический grep `AsyncSessionLocal` без tenant; чеклист для новых задач.

### B7 — Mypy scope

- **Severity:** medium  
- **Влияние:** testability, runtime (косвенно)  
- **Файлы:** `pyproject.toml` `[tool.mypy] files = ...`  
- **Почему опасно:** Ошибки типов в `api/`, `middleware/`, `tasks` не ловятся до runtime.  
- **Как чинить:** Пошаговое добавление пакетов + `[[tool.mypy.overrides]]` для шумных модулей; отдельный CI job `mypy-staged`.

### B8 — Frontend: нет единого server-state слоя

- **Severity:** low–medium  
- **Влияние:** UX, stale state  
- **Файлы:** `frontend/src` (Zustand, локальные hooks)  
- **Почему опасно:** Дублирование loading/error, рассинхрон после мутаций.  
- **Как чинить:** TanStack Query для новых экранов; унификация empty/error (чеклист); не ломать существующие stores в одном PR.

### B9 — Импорт `func` в `api/v1/router.py`

- **Severity:** critical (до фикса)  
- **Статус:** исправлено (`from sqlalchemy import func, select`).

### B10 — Staging secrets

- **Severity:** high (ops)  
- **Статус:** см. `CONFIGURATION_HARDENING.md`; тесты `test_settings_staging_hardening.py`.

---

## Уже подтверждённые тестами (не дублировать без необходимости)

- **TENANT_SCOPE_MISMATCH:** `tests/test_rbac_abac.py` (read/write с чужим `x-tenant`), `tests/test_tenant_security.py` (`test_header_token_tenant_mismatch_denied`).
- **Outbox + tenant webhook routing:** `tests/test_tasks.py` (`test_dispatch_outbox_events_resolves_webhook_endpoints_by_tenant_id`).
- **Idempotency pipeline:** `tests/test_services_pipeline_extra.py`, `tests/test_services_idempotency_unit.py`.
- **S3 key tenant prefix:** `tests/integration/test_tenant_isolation.py`.

---

## Следующий приоритет (после этого спринта)

1. Тесты на `_run_coroutine` (контракт до рефактора) — см. `tests/test_tasks_run_coroutine.py`.  
2. Интеграция: фоновая задача с двумя tenant — нет cross-read.  
3. Узкий ruff gate `--select F821` в CI.  
4. Playwright smoke (локально / opt-in CI) — см. `frontend/e2e/`.

План этапов: `STABILIZATION_PLAN.md`.
