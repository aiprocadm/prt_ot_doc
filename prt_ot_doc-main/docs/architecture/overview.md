# Architecture Overview

## Core vs Modules

**Core платформы**
- `backend/app/api` — HTTP API (FastAPI), входная точка `create_app`.
- `backend/app/core` — конфигурация, лимиты, tracing, logging, metrics.
- `backend/app/services` — бизнес-логика, пайплайны, outbox.
- `backend/app/tasks.py` — Celery-задачи и фоновая обработка.
- `backend/app/models` — доменная модель (SQLAlchemy).

**Модули доменов**
- Документы (`services/pipeline.py`, `tasks.py`, `api/routes/documents.py`)
- Риски (`api/routes/risk.py`, `services/risk_*`)
- PPE / Training / Tasks — отдельные маршруты и сервисы
- Интеграции/webhooks — `services/outbox.py`, `services/webhooks.py`

## Request Flow (API)
1. HTTP запрос → middleware (tenant, rate limit, observability).
2. Валидация Pydantic + доменные проверки.
3. Сервисный слой (DB транзакция).
4. При необходимости: enqueue в outbox / Celery.
5. Стандартизированный ответ с `error_code`, `request_id`.

## Event Flow (Outbox)
1. Сервис формирует событие и пишет запись в `outbox`.
2. `OutboxProcessor` выбирает записи и доставляет webhooks.
3. Ошибки → `FAILED` с backoff, превышение → `DEAD`.
4. Повтор через `/api/v1/admin/outbox/{id}/retry`.
