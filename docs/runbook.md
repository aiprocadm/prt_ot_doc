# Runbook

## Выбор режима запуска

Проект поддерживает два режима:

### Dockerless (fallback)
Используется, когда Docker недоступен (например, в Codespaces без прав на Docker socket).

```bash
make dev:lite
make test:lite
```

Что включено:
- SQLite (`dev.db`) вместо PostgreSQL.
- Локальное хранилище файлов (`./.local_storage`) вместо MinIO/S3.
- Celery в eager-режиме (`CELERY_EAGER=true`), задачи выполняются синхронно.

### Docker
Если Docker доступен, используйте стандартный режим:

```bash
make dev
make test
```

## Ограничения dockerless-режима
- Нет реального Redis (очереди/metrics); задачам Celery назначен eager-режим.
- Presigned URL для скачивания недоступны (требуется MinIO/S3).
- Антивирусные проверки ClamAV не выполняются (используется in-memory очередь).
- Хранилище файлов локальное, без S3-совместимого API.

## Сброс локального состояния (dockerless)
```bash
rm -f dev.db
rm -rf ./.local_storage
```

## Known Codespaces Docker limitation
В Codespaces Docker CLI может отсутствовать или быть недоступен:
```
docker: command not found
make dev → docker: No such file or directory
```
Категория: Docker daemon/CLI отсутствуют в окружении Codespaces без привилегий.
Используйте `make dev:lite` вместо `make dev`.

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

Dockerless вариант:
```bash
make dev:lite
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
make test:lite
pytest --collect-only
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

### Сквозные проверки (E2E smoke)
```bash
curl -H "x-tenant: <tenant>" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/dashboard/summary"

curl -H "x-tenant: <tenant>" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/tasks?overdue=true"

curl -H "x-tenant: <tenant>" -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/tasks?priority=critical"
```

### VS Code Testing (Codespaces)
Если используется Codespaces, панель Testing должна автоматически обнаружить `pytest`
через `.vscode/settings.json`. При проблемах убедитесь, что виртуальное окружение
создано и `requirements-dev.txt` установлены.

## Диагностика
- Healthchecks: `http://localhost:8000/health` и `http://localhost:8000/ready`.
- Метрики: `http://localhost:8000/metrics` (если включены).
- WS stub: `http://localhost:8000/ws/v1/events` (HTTP 501, WebSocket будет в P2).
- Логи Docker: `docker compose logs -f`.
- Структура логов и метрик: см. `docs/ops/observability.md`.
- Дашборд: используйте `GET /dashboard/summary` для проверки агрегатов и ролей доступа.

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
