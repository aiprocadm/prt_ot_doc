# Стабилизация платформы — технический аудит (фактический код)

**Обновлено:** 2026-04-04  
**Метод:** обход `backend/app`, `frontend/src`, `tests/`, CI, `pyproject.toml`; сопоставление с кодом (не с предположениями).

## Краткий audit summary (staff view)

- **Надёжность фона:** главный технический долг — единая точка `_run_coroutine` в `tasks.py` (`asyncio.run` или `Thread` + `asyncio.run` при уже запущенном loop). Это **high** по runtime и отладке; контракт зафиксирован тестами `tests/test_tasks_run_coroutine.py`, но паттерн остаётся хрупким при росте нагрузки и вложенных вызовов.
- **Tenancy:** HTTP-слой и часть фоновых путей усилены (`tenant_row_guard`, `enforce_row_belongs_to_tenant` на jobs/files/webhooks/outbox и т.д.); критичный класс риска — **любой** `session.get(PK)` по tenant-scoped модели без проверки строки аренды (особенно SQLite). Частично закрыто guard’ами в `tasks.py` + `test_tasks_pipeline_run_tenant_guard.py`; нужен **системный** проход по остальным задачам/экспортам.
- **God-files:** `models.py`, `tasks.py`, `router.py`, толстые routes — **medium/high** для maintainability и регрессий; безопасный путь — тесты → вынос в сервисы/пакеты с сохранением URL и схем.
- **Ошибки и observability:** частично structured API errors; много `except Exception` в фоне — **medium**; correlation/tenant в worker-логах — не везде.
- **Статика и CI:** mypy только на `services` + `schemas` — **medium**; integration lane разрежена относительно unit/API — **medium**.
- **Frontend:** Zustand + polling без единого server-state слоя — **low–medium**; стратегия зафиксирована в `ARCHITECTURE_DECISIONS_STABILIZATION.md` (без обязательного React Query в одном PR).

---

## Соответствие заявленным проблемным зонам репозитория

| # | Зона (из ТЗ) | Severity | Влияние | Ключевые файлы | Почему это реальный риск | Безопасное смягчение (без слома контрактов) |
|---|----------------|----------|---------|----------------|----------------------------|---------------------------------------------|
| 1 | Крупные файлы на критическом пути | medium→high | maintainability, testability, runtime (косвенно) | `models/models.py`, `tasks.py`, `api/v1/router.py`, `routes/documents.py`, `routes/risk.py`, `services/pipeline.py`, `services/pipelines_orchestrator.py`, `services/outbox.py` | Сложность ревью, высокая плотность регрессий, сложно локализовать дефект | Этап: тесты-страховка → декомпозиция с re-export / тонкие handlers; не менять публичные пути |
| 2 | Async/sync bridge | **high** | runtime, observability, редко data integrity | `tasks.py` (`_run_coroutine`), `db/session.py` (`Thread` + `asyncio.run` на schema), `core/runtime_bootstrap.py` | Второй event loop, daemon thread, неочевидные deadlock/retry | Сохранить контрактные тесты; логировать bridge/duration; поэтапно уводить hot path с вложенного loop |
| 3 | Broad `except` | medium | observability, retry semantics | `tasks.py`, `pipeline.py`, webhooks, часть routes | Тихие сбои, неверные повторы, сложные инциденты | Сужение типов; разделение transient vs terminal; infra-guard только на границе |
| 4 | Tenant end-to-end | **high** | tenancy, security | middleware, `tenant_row_guard`, `tasks.py`, pipelines, exports, webhooks, outbox | Cross-tenant через фон или `get(PK)` | Продолжать row-level guard; прокидывать `tenant_id` в сессию задач; интеграционные тесты «два tenant» |
| 5 | Узкий mypy | medium | testability | `pyproject.toml` → `files = services, schemas` | Ошибки типов в API/tasks до prod | Staged расширение + overrides |
| 6 | Мало integration tests | medium | testability | `tests/`, `tests/integration/` | Дыры в сквозных сценариях | Приоритет: tenant + outbox + jobs + permissions |
| 7 | Playwright минимален | low→medium | UX, регрессия UI | `frontend/e2e/` | Пропуск багов auth/tenant/doc flow | Расширить smoke: login, list, detail, 403, logout |
| 8 | Frontend server-state | low→medium | UX, consistency | Zustand, `useAsyncResource`, `usePolling` | Рассинхрон после мутаций, polling edge cases | Документированная стратегия (ADR); унификация loading/error без смены стека |

---

## Executive summary (агрегированная таблица)

| Зона | Severity (агрегат) | Комментарий |
|------|-------------------|-------------|
| God-files на критическом пути | **medium → high** | См. зона #1 |
| Async/sync bridges | **high** | См. зона #2 |
| Broad `except` в фоне/API | **medium** | См. зона #3 |
| Tenant HTTP | **низкий–средний** | Middleware + тесты; усиление row-guards на API |
| Tenant фон / ORM | **high** (остаточный) | Guard’ы частично; нужен полный аудит `get(PK)` в workers |
| Mypy | **medium** | См. зона #5 |
| Integration / E2E | **medium** | См. зоны #6–7 |
| Frontend server-state | **low–medium** | ADR; без big bang React Query |
| Observability | **medium** | correlation/tenant/metrics в workers |

---

## R1 — Крупные файлы (god-files)

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R1.1 | medium | maintainability, testability | `backend/app/models/models.py` | Смешение доменов, сложные merge | Вынос новых сущностей в `modules/*` + re-export из `models.py`; не менять имена таблиц |
| R1.2 | medium | maintainability, runtime | `backend/app/tasks.py` | Регрессии Celery, сложные зависимости | Пакет `app/tasks/*.py` + re-export имён задач для autodiscover |
| R1.3 | medium | maintainability | `backend/app/api/v1/router.py`, `api/routes/documents.py`, `risk.py`, … | Толстые handlers | Вынести use-case в `services/`; маршруты оставить тонкими |
| R1.4 | medium | maintainability | `backend/app/services/pipeline.py`, `pipelines_orchestrator.py`, `outbox.py` | Ядро генерации и доставки | Разделить orchestration / execution / dispatch после тестов |

---

## R2 — Async/sync bridge

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R2.1 | **high** | runtime, observability | `backend/app/tasks.py` — `_run_coroutine` | Daemon thread + отдельный `asyncio.run` при активном loop | Контрактные тесты `test_tasks_run_coroutine.py`; debug-лог bridge/duration; долгосрочно — отдельный async worker или чёткая изоляция entrypoints |
| R2.2 | **high** | runtime, data integrity (инициализация) | `backend/app/db/session.py` | `Thread` + `asyncio.run` на schema ops | Убедиться, что не на per-request path; документировать startup-only |
| R2.3 | medium–high | runtime | `backend/app/core/runtime_bootstrap.py` | Дублирование bridge | Единый helper + контракт «до старта loop» |

---

## R3 — Broad exception handling

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R3.1 | medium | observability, data integrity | `tasks.py`, `pipeline.py`, webhooks | Потеря причины, неверные retry | Сужение типов; `logger.exception` + extra; terminal vs transient |

---

## R4 — Tenant safety end-to-end

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R4.1 | **high** (класс) | tenancy, security | `tasks.py` — `_generate_document_for_run` и др. | PK `session.get` без проверки tenant строки | Guard: `assert_tenant_row_matches_session` / аналоги; тесты `test_tasks_pipeline_run_tenant_guard.py` |
| R4.2 | high | tenancy | outbox, webhooks, exports, batch | Неверный `tenant_slug` в kwargs задачи | Проверка row vs `session.info["tenant_id"]` при каждом load чувствительной сущности |
| R4.3 | medium | observability | workers | Нет tenant в логах | `extra={"tenant_slug", "tenant_id", "correlation_id"}` на старте задачи |

---

## R5 — Статический анализ

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R5.1 | medium | testability | `pyproject.toml` `[tool.mypy] files` | Ошибки типов в API/tasks до runtime | Staged: `api/deps` → `middleware` → `core` → `tasks`; overrides для шума |
| R5.2 | medium | testability | Ruff на весь `backend/app` | Большой бэклог | Узкий gate `F821` в CI, затем расширение |

---

## R6 — Тесты и регрессия

| ID | Severity | Влияние | Комментарий |
|----|----------|---------|-------------|
| R6.1 | medium | testability | Integration: два tenant + outbox + webhook + job — нарастить |
| R6.2 | low–medium | UX | Playwright: документы, forbidden, logout, minimal generate |

---

## R7 — Frontend

| ID | Severity | Влияние | Комментарий |
|----|----------|---------|-------------|
| R7.1 | low–medium | UX | Единые loading/error; см. `ARCHITECTURE_DECISIONS_STABILIZATION.md` |
| R7.2 | low | maintainability | Без глобальной миграции на React Query в одном PR |

---

## R8 — Observability / SRE

| ID | Severity | Влияние | Комментарий |
|----|----------|---------|-------------|
| R8.1 | medium | observability | correlation / tenant в job-логах; метрики webhook/queue |
| R8.2 | medium | security | Маскирование PII в логах; runbook recovery — `RUNBOOK_STABILIZATION.md` |

---

## Уже подтверждённые тестами (инвентаризация)

- **TENANT_SCOPE_MISMATCH / header vs JWT:** `test_tenant_security.py`, `test_rbac_abac.py`, `test_auth_tenant_header_enforcement.py`
- **Защищённые маршруты / permissions:** множество `test_next*_`, `test_api_*`, `routeGroups` на frontend
- **Jobs API row + tenant:** `enforce_row_belongs_to_tenant`; регрессия cross-tenant: `tests/test_jobs_api.py::test_get_job_returns_404_when_job_belongs_to_different_tenant`
- **Outbox dedup / dispatch:** `test_outbox_dispatch.py`, `test_next43_outbox_webhooks.py`
- **Pipeline / idempotency:** `test_services_pipeline_extra.py`, `test_services_idempotency_unit.py`, `tests/integration/test_pipeline_*`, `tests/test_next10_job_engine.py`
- **Документ generation / readiness:** `test_documents_generate.py`, `tests/test_document_readiness_unit.py` (в т.ч. `pipeline_stages` / `render_docx` detail)
- **401 / redirect (frontend):** `errorHandlingAuthRedirect.test.ts`
- **Celery bridge:** `tests/test_tasks_run_coroutine.py`
- **Pipeline run + batch tenant guard (фон):** `tests/test_tasks_pipeline_run_tenant_guard.py`

---

## Следующий приоритет (что делать дальше)

1. **Интеграция:** сценарий «два tenant» — чтение чужого job/document/outbox → стабильный 404/403 + лог `*_tenant_scope_mismatch`.
2. **Фон:** пройти оставшиеся задачи в `tasks.py` с `session.get` по tenant-моделям — чеклист как для `_generate_document_for_run`.
3. **Retry / terminal semantics:** явная матрица в коде + короткий ADR для outbox/Celery.
4. **Mypy staged** + узкий **ruff F821** на `backend/app`.
5. **Playwright:** список документов, карточка, 403, logout (при доступном стенде).

Пошаговый план этапов 1–10: `STABILIZATION_PLAN.md`. Риски релиза: `REGRESSION_RISKS_AND_MITIGATIONS.md`. Пробелы тестов: `TEST_COVERAGE_GAPS.md`. Операции: `RUNBOOK_STABILIZATION.md`.
