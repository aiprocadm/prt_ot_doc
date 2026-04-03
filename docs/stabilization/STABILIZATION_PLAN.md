# План стабилизации (этапы 1–10)

Принципы: не ломать публичные API и tenant-модель; **сначала тесты и наблюдаемость**, затем рефакторинг; атомарные PR; спорные решения — в `ARCHITECTURE_DECISIONS_STABILIZATION.md`.

---

## Этап 1 — Аудит (документация)

- [x] Актуализировать `STABILIZATION_AUDIT.md` (severity, влияние, файлы, риск, смягчение).
- [x] Актуализировать `STABILIZATION_PLAN.md` (этапы 1–10).
- Корневые указатели: `STABILIZATION_AUDIT.md`, `STABILIZATION_PLAN.md` в корне репозитория.

## Этап 2 — Тесты до рефакторинга

- [x] Контракт `_run_coroutine` — `tests/test_tasks_run_coroutine.py`.
- [x] Tenant guard для `PipelineRun` в фоне — `tests/test_tasks_pipeline_run_tenant_guard.py`.
- [x] Batch item / batch run + `generate_document_task` failure path: PK + `tenant_id` (`_assert_batch_item_scope`, guard в `_mark_failed`).
- [x] `apply_headers_job` (`DocumentJob`, `DocumentVersion`), `convert_pdf_job` (`PdfConversionRun`, `File`), `edo_status_simulation_job` (`EdoMessage`), inbound EDO webhook (`DocumentVersion` по `envelope.object_id`).
- [ ] Остальные модули вне `tasks.py` с `session.get` по tenant-моделям — точечный аудит.
- [ ] Интеграция: два tenant + outbox + webhook (HTTP или task-level).
- [ ] Frontend: logout / stale token (Vitest), не дублируя существующий `errorHandlingAuthRedirect`.

## Этап 3 — Background / reliability

- [x] Structured debug-логи для `_run_coroutine` (bridge, duration).
- [ ] Единая политика retry / terminal failure (документ + код в `outbox` / Celery).
- [ ] Свести дубли bridge в `runtime_bootstrap` и `tasks` (осторожно).
- [ ] Убрать или изолировать `asyncio.run` на путях, которые могут вызываться при уже работающем loop (поэтапно).

## Этап 4 — Tenant safety end-to-end

- [x] Guard: `run.tenant_id` vs `session.info["tenant_id"]` в `_generate_document_for_run`.
- [ ] Аудит остальных задач с `session.get(..., id)` по tenant-моделям.
- [ ] Прокидывание `tenant_id` / `correlation_id` в structured logs задач.

## Этап 5 — God-files

- [ ] `app/tasks/` + compatibility re-exports.
- [ ] Тонкие route handlers для documents, risk, packs, jobs, files, approvals, workspace, webhooks.
- [ ] `models.py` — только re-exports для новых моделей.

## Этап 6 — Error handling

- [ ] Единый контракт API error (code, type, message, field_errors, correlation_id).
- [ ] Сузить `except Exception` в бизнес-слое; верхний infra-guard + логирование.

## Этап 7 — Static checks / CI

- [ ] `mypy` staged (см. `STABILIZATION_AUDIT` R5).
- [ ] Ruff: начать с `F821` на `backend/app`.
- [ ] Регрессионные smoke gates (критические пути) — по мере готовности стенда.

## Этап 8 — Integration + E2E

- [ ] Integration: tenant, outbox, webhooks, jobs, permissions, document flow (расширение существующих `tests/integration/`).
- [x] Playwright каркас: `frontend/e2e/smoke.spec.ts`, workflow `e2e-smoke.yml`.
- [ ] Playwright: список документов, детали, минимальный generate/polling, forbidden, logout.

## Этап 9 — Frontend stabilization

- [ ] Auth bootstrap, redirect loops, tenant/token coherence — точечно.
- [ ] Унификация loading/error/empty без смены глобального state-стека.
- [x] Стратегия server-state без React Query — зафиксирована в ADR.

## Этап 10 — Observability / runbook

- [ ] Метрики: очередь, retries, webhooks, pipeline stages.
- [ ] Health/readiness, отсутствие PII в логах.
- [x] Обновлять `RUNBOOK_STABILIZATION.md` при изменении recovery paths.

---

## Легаси-фазы (краткая карта)

Для обратной совместимости с прежними названиями в чатах:

| Старые «фазы 0–6» | Соответствие |
|-------------------|--------------|
| Фаза 0 | Этапы 1–2 |
| Фаза 1 | Этап 7 |
| Фаза 2 | Этап 5 |
| Фаза 3 | Этап 3 |
| Фаза 4 | Этап 9 |
| Фаза 5 | Этап 8 |
| Фаза 6 | Этап 10 |
