# План стабилизации (этапы 1–10)

**Обновлено:** 2026-04-04  

Принципы: не ломать публичные API и tenant-модель; **сначала тесты и наблюдаемость**, затем рефакторинг; атомарные PR; спорные решения — в `ARCHITECTURE_DECISIONS_STABILIZATION.md`.

Корневые указатели репозитория: [STABILIZATION_AUDIT.md](../../STABILIZATION_AUDIT.md) → этот документ в `docs/stabilization/`.

---

## Этап 1 — Аудит по реальному коду (документация)

**Цель:** зафиксировать риски, severity, влияние, файлы, безопасный способ исправления.

| Действие | Статус |
|----------|--------|
| `STABILIZATION_AUDIT.md` — матрица 8 зон + R1–R8 | [x] |
| `STABILIZATION_PLAN.md` — этапы 1–10 | [x] |
| `REGRESSION_RISKS_AND_MITIGATIONS.md` | [x] актуализировать при каждом крупном изменении фона/tenant |
| `TEST_COVERAGE_GAPS.md` | [x] |
| `RUNBOOK_STABILIZATION.md` | [x] |

---

## Этап 2 — Зафиксировать критичные зоны тестами (до крупного рефакторинга)

| Область | Статус | Артефакты / тесты |
|---------|--------|-------------------|
| Tenant isolation (API) | частично | Расширить HTTP integration «чужой ресурс» |
| X-Tenant vs JWT scope | частично | `test_auth_tenant_header_enforcement`, `test_tenant_security` |
| Protected routes / guards | частично | RBAC/ABAC тесты, `test_next*` |
| Background jobs happy/fail/retry | частично | `test_tasks_run_coroutine`, `test_tasks_pipeline_run_tenant_guard`, `test_next10_job_engine` |
| Pipeline execution | частично | `backend/tests/test_next39_pipeline_orchestrator.py`, integration pipeline |
| Outbox processing | частично | `test_outbox_dispatch`, `test_next43_outbox_webhooks` |
| Webhook deduplication | частично | Усилить при изменении `webhooks` / inbound tasks |
| Idempotency | частично | `test_services_idempotency_unit`, `test_next10_job_engine` |
| Document generation happy path | частично | `test_documents_generate`, readiness — `test_document_readiness_unit` |
| 401/403 flows | частично | API + `errorHandlingAuthRedirect.test.ts` |
| Frontend auth bootstrap / stale token | частично | Добавить сценарии без дублирования существующих тестов |

**Открыто:** интеграция «два tenant» для outbox + job; Playwright beyond smoke.

---

## Этап 3 — Background / reliability слой

**Фокус:** `tasks.py`, `pipeline.py`, `pipelines_orchestrator.py`, `outbox.py`, `db/session.py`, `runtime_bootstrap.py`.

| Действие | Статус |
|----------|--------|
| Structured debug `_run_coroutine` (bridge, duration) | [x] |
| Документ: retry vs terminal (outbox + Celery) | [ ] |
| Свести дубли bridge (`runtime_bootstrap` vs `tasks`) | [ ] |
| Убрать/изолировать опасные вызовы при вложенном loop | [ ] поэтапно |
| Явные retry semantics / terminal failure | [ ] |
| Разделение orchestration / execution / reconciliation | [ ] после тестов |

---

## Этап 4 — Tenant safety end-to-end

| Действие | Статус |
|----------|--------|
| Guard PipelineRun vs session tenant (`tasks`) | [x] |
| Row-level enforcement на чувствительных API (jobs, files, …) | частично [x] |
| Аудит всех worker путей с `session.get(PK)` | [ ] |
| `tenant_id` / `correlation_id` в structured logs задач | [ ] |
| Integration tests подтверждают изоляцию | [ ] |

---

## Этап 5 — Сократить god-files (без слома API)

| Действие | Статус |
|----------|--------|
| `app/tasks/*.py` + compatibility re-exports | [ ] |
| Тонкие handlers: documents, risk, packs, jobs, files, approvals, workspace, webhooks | [ ] |
| `models.py` — re-exports для новых модулей | [ ] по мере появления сущностей |

---

## Этап 6 — Нормализовать error handling

| Действие | Статус |
|----------|--------|
| Единый контракт: code, type, message, details, field_errors, correlation_id | [ ] выровнять с `error_handlers.py` |
| Предсказуемые HTTP status | [ ] |
| Без silent swallow в бизнес-слое | [ ] |
| Нет утечки raw traceback наружу | [ ] |
| Broad except только на infra boundary + обязательный structured log | [ ] |

---

## Этап 7 — Static checks и CI quality gates

| Действие | Статус |
|----------|--------|
| Mypy staged за пределы `services`/`schemas` | [ ] |
| Ruff F821 (или эквивалент) на `backend/app` | [ ] |
| Документировать staged scope в ADR / audit | [ ] |
| Регрессионные smoke gates на critical paths | [ ] |

---

## Этап 8 — Integration и E2E

| Действие | Статус |
|----------|--------|
| Integration: tenant, outbox, webhooks, jobs, permissions, document flow | [ ] расширение `tests/integration/` |
| Playwright каркас | [x] `frontend/e2e/smoke.spec.ts`, workflow `e2e-smoke.yml` |
| Playwright: login errors, documents list/detail, minimal generate, 403, logout | [ ] |

---

## Этап 9 — Frontend stabilization

| Действие | Статус |
|----------|--------|
| Auth bootstrap, redirect loops, tenant/token coherence | [ ] точечно |
| Stale UI после мутаций, polling edge cases | [ ] |
| Единообразие loading/error/empty + permissions | [ ] |
| Стратегия server-state без React Query | [x] ADR |

---

## Этап 10 — Observability и эксплуатационная зрелость

| Действие | Статус |
|----------|--------|
| Correlation propagation end-to-end | [ ] частично |
| Tenant-aware logging в workers | [ ] |
| Метрики: jobs, pipeline, webhooks, очередь | [ ] |
| Health/readiness | [ ] сверить с деплоем |
| PII в логах — запрет / маскирование | [ ] |
| Runbook recovery | [x] база в `RUNBOOK_STABILIZATION.md` — обновлять при изменениях |

---

## Легаси-фазы (краткая карта)

| Старые «фазы 0–6» | Соответствие |
|-------------------|--------------|
| Фаза 0 | Этапы 1–2 |
| Фаза 1 | Этап 7 |
| Фаза 2 | Этап 4 |
| Фаза 3 | Этап 3 |
| Фаза 4 | Этап 6 |
| Фаза 5 | Этап 5 |
| Фаза 6 | Этапы 8–10 |
