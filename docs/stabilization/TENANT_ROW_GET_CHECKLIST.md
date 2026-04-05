# Чеклист: ID из path/body/очереди → `session.get` без tenant в SQL

## Риск

На SQLite (одна схема) `AsyncSession.get(Model, pk)` может вернуть строку **другого** тенанта: в запросе нет фильтра `tenant_id`. На Postgres с `search_path` по схеме тенанта это частично смягчается, но защита в коде остаётся нужной для тестов, Celery и смешанных конфигураций.

## Правило

Для каждой цепочки **идентификатор извне** (path, query, JSON body, заголовки, kwargs Celery, outbox payload):

1. После `session.get(..., id)` убедиться, что строка относится к текущему тенанту.
2. Предпочтительно: **`assert_tenant_row_matches_session`** из `app/db/tenant_row_guard.py` (с `expected_tenant_id` для API, если в `session.info` может не быть `tenant_id`).
3. В HTTP-роутах: **`enforce_row_belongs_to_tenant`** из `app/api/tenant_row_http.py` после проверки «строка не `None`».
4. Альтернатива/дополнение: выборка через `select(...).where(Model.id == id, Model.tenant_id == ...)` вместо голого `get` по PK.

## Закрытые hot-path (по состоянию репозитория)

| Область | Файлы / точки |
|--------|----------------|
| Jobs API | `app/api/routes/jobs.py` — `DocumentJob`, `DocumentJobStep`, `FileRecord` (логи шага), `PipelineProfile` при создании |
| Files API | `app/api/routes/files.py` (`StoredFile`), `app/modules/files/api.py` (`FileRecord` — get / reindex) |
| Webhooks | `app/api/routes/webhooks.py` — `WebhookEndpoint`, `WebhookDelivery`, `Outbox` (replay) |
| Outbox admin | `app/api/routes/outbox_admin.py` — `Outbox`, `OutboxEvent` |
| Documents generate | `app/api/routes/documents.py` — `_ensure_company` / `_ensure_person` (`Company` / `Person`) |
| Templates API (v1 router) | `app/api/v1/router.py` — `POST /templates/{id}/versions` (legacy multipart): после исправления 2026-04-05 проверка `_tenant_scope` + `deleted_at`, как у catalog/upload; preview повторно валидирует `Template` |
| Pipelines HTTP | `app/modules/pipelines/api.py` — retry шага: `DocumentJobStep.tenant_id` должен совпадать с текущим тенантом |
| Фоновые задачи | `app/tasks/` (`_core.py`), `app/celery/tasks/*`, `app/services/pipelines_orchestrator.py`, `app/modules/pipelines/orchestrator.py` |

## Бэклог для аудита

Прогнать поиск `session.get` в `app/api/`, `app/modules/`, `app/services/` и для каждого вызова отметить: источник id, есть ли фильтр по тенанту или guard. Особое внимание: `app/api/v1/router.py` (шаблоны), `app/modules/pipelines/api.py`, `app/modules/files/*`, EDO/approval маршруты.

## Связанные документы

- `ARCHITECTURE_DECISIONS_STABILIZATION.md` — решение по `assert_tenant_row_matches_session` и фоновым путям.
