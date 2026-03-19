# Setup

## Environment
Start from `.env.example` in repo root and `backend/.env.example`.

Key variables:
- `DATABASE_URL`
- `REDIS_URL`
- `REDIS_RESULT_URL`
- `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `APP_ENV`
- `ADMIN_BOOTSTRAP`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`

## Install
```bash
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## Run
```bash
uvicorn backend.app.main:app --reload
npm --prefix frontend run dev
```

## Migrations
```bash
alembic -c backend/app/migrations/alembic.ini upgrade head
```

## Workers
```bash
celery -A backend.app.worker worker --loglevel=info
```
