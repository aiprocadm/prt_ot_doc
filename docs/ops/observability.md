# Observability & Debugging

## Быстрый старт
- Метрики доступны на `/metrics` (если `ENABLE_METRICS=1`).
- Структурные логи включают `request_id`, `trace_id`, `tenant_id`, `user_id`.
- Health endpoints: `/health`, `/ready`.

## Логи
Все запросы и фоновые задачи логируются в JSON-формате (если `LOG_JSON=1`) и включают:
- `request_id` / `trace_id`
- `tenant_id`
- `user_id` (если доступен)
- `task_id` (для Celery)

Проверяйте поля `error_class`, `status_code`, `outbox_id` в ошибках доставки webhook'ов.

## Ключевые метрики

### Документооборот
- `pipeline_requests_total{pipeline="document",stage="..."}` — этапы пайплайна.
- `pipeline_stage_duration_seconds{pipeline="document",stage="..."}` — длительность этапов.
- `documents_generated_total` — количество успешных генераций.

### Outbox / Webhooks
- `outbox_enqueued_total` — события поставлены в очередь.
- `outbox_sent_total` — успешно доставленные.
- `outbox_failed_total` — ошибки доставки (retry).
- `outbox_dead_total` — dead-letter после превышения `OUTBOX_MAX_ATTEMPTS`.
- `outbox_attempts_histogram` — распределение попыток.
- `outbox_dispatch_latency_seconds` — задержка между созданием и доставкой.

### Обязательства / Напоминания
События `TaskDueSoon` и `TaskOverdue` публикуются через outbox:
- фильтруйте `outbox_*` метрики по `event_type="TaskDueSoon"` или `event_type="TaskOverdue"`.

### HTTP / Celery
- `http_requests_total`, `http_request_errors_total`
- `http_request_latency_seconds`, `http_request_latency_p95_seconds`
- `celery_tasks_enqueued_total`, `celery_task_duration_seconds`
- `celery_queue_depth` и `celery_task_latency_p95_seconds`

## Что смотреть, когда что-то ломается

1. **Ошибки генерации документов**
   - `pipeline_errors_total{pipeline="document"}`
   - `pipeline_stage_duration_seconds{stage="docx_generated|pdf_converted|stored_s3"}`
   - Логи `generate_document_task failed` с `request_id`

2. **Webhooks не доходят**
   - `outbox_failed_total`, `outbox_dead_total`
   - Записи `/api/v1/admin/outbox?status=FAILED` и `last_error`
   - Проверьте `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_RETRY_BACKOFF_SECONDS`

3. **Напоминания по обязательствам**
   - Запуск `tasks.reminders.dispatch` (Celery beat)
   - Outbox события `TaskDueSoon`/`TaskOverdue`

4. **Сбойные запросы API**
   - `http_request_errors_total{status="4xx|5xx"}`
   - Ошибки с `error_code` в ответах API
