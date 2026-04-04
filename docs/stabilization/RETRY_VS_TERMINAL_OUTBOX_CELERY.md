# Retry vs terminal: outbox и Celery-задачи

**Обновлено:** 2026-04-04  

Цель: одна точка правды по **когда снова пытаемся**, а **когда считаем ошибку окончательной**, без дублирования бизнес-логики в чатах.

## Исходящий webhook / таблица `Outbox` (`OutboxProcessor`)

| Исход | Статус строки | Поведение |
|-------|----------------|-----------|
| Успешный HTTP dispatch | `SENT` | Конец, `next_attempt_at = None` |
| Сетевой сбой, таймаут, `httpx` errors | `FAILED` | Повтор по `next_attempt_at`, backoff (`outbox_retry_*`, `outbox_max_attempts`) |
| HTTP **5xx**, **408**, **429** | `FAILED` | То же (транзиент с точки зрения доставки) |
| HTTP **4xx** (кроме отнесённых к retry выше) | `DEAD` | Терминально для этой попытки доставки; ручной retry через admin API (`FAILED`/`DEAD` → `PENDING`) |
| Превышен `outbox_max_attempts` | `DEAD` | Терминально по политике попыток |

Реализация: `_classify_http_error` и ветки `_mark_failed` / `_mark_dead` в `backend/app/services/outbox.py`.

## Задачи Celery (`app.tasks`)

| Механизм | Назначение |
|----------|------------|
| `autoretry_for=RETRYABLE_EXCEPTIONS` | Повтор **всей задачи** при инфраструктурных сбоях: `ClientError`, `SQLAlchemyError`, `OSError`, `asyncio.TimeoutError` |
| `retry_backoff` / `retry_backoff_max` / `retry_jitter` | Экспоненциальный backoff между **Celery**-повторами |
| `retry_kwargs.max_retries` | Потолок повторов **на уровне задачи** (`settings.celery.task_max_retries`) |

Исключения **вне** `RETRYABLE_EXCEPTIONS` (ошибки валидации, доменные `ValueError` после guard’ов и т.д.) **не** получают автоповтор Celery — это сознательный «terminal path» на уровне задачи (состояние в БД обновляется внутри `_run`, если предусмотрено).

Константа: `RETRYABLE_EXCEPTIONS` в `backend/app/tasks.py` (рядом с декораторами задач).

## Связь слоёв

- **Outbox** отвечает за доставку на внешний URL и классификацию HTTP.
- **Celery** (`outbox.dispatch` и др.) может упасть до/после процессора; повтор задачи **не заменяет** внутренние статусы строки outbox, но даёт ещё один проход `process_once`.

Дальнейшие изменения политики — править таблицу здесь и соответствующий код в одном PR.
