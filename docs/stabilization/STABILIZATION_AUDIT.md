# Стабилизация платформы — технический аудит (фактический код)

**Дата:** 2026-04-03  
**Метод:** обход `backend/app`, `frontend/src`, `tests/`, CI, `pyproject.toml`; точечные правки с тестами.

## Executive summary

| Зона | Severity (агрегат) | Комментарий |
|------|-------------------|-------------|
| God-files на критическом пути | **medium → high** | Рост сложности ревью и регрессий; см. R1 |
| Async/sync bridges | **high** | `asyncio.run` / `Thread` в Celery и `db/session.py`; см. R2 |
| Broad `except` в фоне/API | **medium** | Риск тихих сбоев и неверных retry; см. R3 |
| Tenant HTTP | **низкий риск** | Middleware + `TENANT_SCOPE_MISMATCH` хорошо покрыты тестами |
| Tenant фон / ORM | **high** (была дыра) | На SQLite `get(PK)` не изолирует tenant; добавлен guard в `_generate_document_for_run`; см. R4 |
| Mypy | **medium** | Только `services` + `schemas`; см. R5 |
| Integration / E2E | **medium** | Много unit/API тестов; отдельный «тяжёлый» контур разрежен; Playwright — минимальный smoke |
| Frontend server-state | **low–medium** | Zustand + `useAsyncResource` / `usePolling`; без React Query; стратегия — ADR |
| Observability | **medium** | Метрики частично; не везде tenant/correlation в worker-логах |

---

## R1 — Крупные файлы (god-files)

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R1.1 | medium | maintainability, testability | `backend/app/models/models.py` | Смешение доменов, сложные merge | Вынос новых сущностей в `modules/*` + re-export из `models.py`; не менять имена таблиц |
| R1.2 | medium | maintainability, runtime | `backend/app/tasks.py` | Регрессии Celery, сложные зависимости | Пакет `app/tasks/*.py` + re-export имён задач для autodiscover |
| R1.3 | medium | maintainability | `backend/app/api/v1/router.py`, `api/routes/documents.py`, `risk.py`, … | Толстые handlers | Вынести use-case в `services/`; маршруты оставить тонкими |
| R1.4 | medium | maintainability | `backend/app/services/pipeline.py` | Ядро генерации | Разделить orchestration / execution после тестов |

---

## R2 — Async/sync bridge

| ID | Severity | Влияние | Файлы | Почему риск | Безопасное исправление |
|----|----------|---------|-------|-------------|-------------------------|
| R2.1 | high | runtime, observability | `backend/app/tasks.py` — `_run_coroutine` | Daemon thread + отдельный `asyncio.run` | Контрактные тесты; debug-лог bridge/duration; долгосрочно — async worker / отдельный процесс |
| R2.2 | high | runtime, data integrity | `backend/app/db/session.py` | `Thread` + `asyncio.run` на schema ops | Убедиться, что не на hot path запроса; CLI/async split |
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
| R4.1 | **high** (до guard) | tenancy, security | `tasks.py` — `_generate_document_for_run` | PK `session.get` на SQLite видит чужой tenant | **Исправлено:** `_assert_pipeline_run_matches_session_tenant`; тесты `test_tasks_pipeline_run_tenant_guard.py` |
| R4.2 | high | tenancy | outbox, webhooks, exports, batch tasks | Неверный `tenant_slug` в job | **Частично:** guards в `tasks.py` для batch, PDF run/file, `DocumentJob`/`DocumentVersion`, EDO message; outbox/webhooks/export — отдельный аудит |
| R4.3 | medium | observability | workers | Нет tenant в логах | Прокидывать `tenant_slug`/`tenant_id` в `extra` при старте задачи |

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
| R6.1 | medium | testability | Integration lane для tenant+job+outbox — нарастить |
| R6.2 | low–medium | UX | Playwright: расширить сценарии (документы, logout, 403 UI) |

---

## R7 — Frontend

| ID | Severity | Влияние | Комментарий |
|----|----------|---------|-------------|
| R7.1 | low–medium | UX | Единые loading/error; см. `ARCHITECTURE_DECISIONS_STABILIZATION.md` (server-state) |
| R7.2 | low | maintainability | Без глобальной миграции на React Query в одном PR |

---

## R8 — Observability / SRE

| ID | Severity | Влияние | Комментарий |
|----|----------|---------|-------------|
| R8.1 | medium | observability | correlation / tenant в job-логах; метрики webhook/queue |
| R8.2 | medium | security | Маскирование PII в логах; runbook recovery |

---

## Уже подтверждённые тестами (инвентаризация)

- **TENANT_SCOPE_MISMATCH / header vs JWT:** `test_tenant_security.py`, `test_rbac_abac.py`, `test_auth_tenant_header_enforcement.py`
- **Защищённые маршруты / permissions:** множество `test_next*_`, `test_api_*`, `routeGroups` на frontend
- **Outbox dedup:** `test_outbox_dispatch.py`, `test_next43_outbox_webhooks.py`
- **Pipeline / idempotency:** `test_services_pipeline_extra.py`, `test_services_idempotency_unit.py`, `tests/integration/test_pipeline_*`
- **Документ generation:** `test_documents_generate.py`, API-тесты
- **401 / redirect (frontend):** `errorHandlingAuthRedirect.test.ts`
- **Celery bridge:** `test_tasks_run_coroutine.py`
- **Pipeline run + batch item tenant guard (фон):** `test_tasks_pipeline_run_tenant_guard.py`

---

## Следующий приоритет

1. Аналогичные **PK + tenant** проверки для других фоновых путей (batch item, jobs по `run_id`).  
2. Интеграционный тест: **outbox dispatch** с двумя tenant.  
3. **Mypy staged** + узкий **ruff F821**.  
4. Расширение **Playwright** при наличии стенда.

Пошаговый план: `STABILIZATION_PLAN.md`.
