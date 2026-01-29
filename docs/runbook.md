# Runbook

## Локальный запуск

### Подготовка
```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Одной командой
```bash
make dev
```

### Остановка
```bash
docker compose down
```

Для остановки локальных процессов (если запускались вручную):
```bash
pkill -f "uvicorn app.main:app"
pkill -f "celery -A app.services.celery_app.celery_app"
```

### Инфраструктура
```bash
docker compose up -d db redis minio
```

### Миграции
```bash
PYTHONPATH=backend python -m alembic -c backend/app/migrations/alembic.ini upgrade head
```

### Backend
```bash
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Celery воркеры
```bash
celery -A app.services.celery_app.celery_app worker \
  --queues default,notifications --loglevel INFO

celery -A app.services.celery_app.celery_app worker \
  --queues pdf --loglevel INFO

celery -A app.services.celery_app.celery_app beat --loglevel INFO
```

### Очистка idempotency (TTL)
Запускайте периодически (например, раз в сутки) для удаления завершённых ключей старше
`IDEMPOTENCY_TTL_DAYS`:
```bash
celery -A app.services.celery_app.celery_app call idempotency.cleanup
```

### Обязательства и напоминания
1. Убедитесь, что запущен `celery beat` (задача `tasks.reminders.dispatch` выполняется ежедневно).
2. Настройте окна напоминаний на уровне tenant:
   - поле `tenant.settings.obligations.reminder_days` (например `[30, 14, 7]`).
3. Для проверки вручную:
   - создайте инспекцию/аттестацию с датой в ближайшие дни;
   - дождитесь выполнения `tasks.reminders.dispatch`;
   - проверьте `outbox` на события `TaskDueSoon`/`TaskOverdue`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Основные проверки

### Backend тесты
```bash
make test
```

### Линт и форматирование
```bash
make lint
make format
```

### Frontend проверки
```bash
cd frontend
npm run lint
npm run test
npm run build
```

## Диагностика
- Healthchecks: `http://localhost:8000/health` и `http://localhost:8000/ready`.
- Метрики: `http://localhost:8000/metrics` (если включены).
- WS stub: `http://localhost:8000/ws/v1/events` (HTTP 501, WebSocket будет в P2).
- Логи Docker: `docker compose logs -f`.
- Структура логов и метрик: см. `docs/ops/observability.md`.

## Ручное воспроизведение outbox
1. Найдите застрявшую запись:
```bash
curl -H "x-tenant: <tenant>" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/admin/outbox?status=FAILED"
```
2. Повторите доставку:
```bash
curl -X POST -H "x-tenant: <tenant>" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/admin/outbox/<outbox_id>/retry"
```

## Типовые проблемы
- **Frontend не стартует**: убедитесь, что `VITE_API_BASE_URL` указывает на доступный backend (например, `http://localhost:8000/api`).
- **Ошибки миграций**: проверьте доступность базы (`docker compose ps`) и переменные `POSTGRES_*` в `.env`.
- **Очереди зависли**: проверьте Redis (`docker compose logs redis`) и значения `WORKER_QUEUES`/`PDF_WORKER_QUEUE`.
- **Напоминания по задачам не шлются**: убедитесь, что запущен `celery beat` (задача `tasks.reminders.dispatch` запускается ежедневно).
- **Webhooks не доставляются**: проверьте очередь `outbox` и журнал ошибок (поле `last_error`).
