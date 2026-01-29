# Runbook

## Локальный запуск

### Подготовка
```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
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
```

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
- Логи Docker: `docker compose logs -f`.
