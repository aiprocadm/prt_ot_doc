# Setup

## Required services
- PostgreSQL
- Redis
- S3/MinIO-compatible object storage
- Celery worker runtime
- LibreOffice headless for DOCX→PDF
- ClamAV if file scanning is enabled

## Important environment variables
- `DATABASE_URL`
- `REDIS_URL`
- `REDIS_RESULT_URL`
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `APP_ENV`
- `ADMIN_BOOTSTRAP`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `ADMIN_TENANT`

## Install
```bash
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci
```

## Run backend
```bash
alembic -c backend/app/migrations/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run frontend
```bash
npm --prefix frontend run dev
```

## Run worker
```bash
celery -A backend.app.worker worker --loglevel=info
```

## High-value validation
```bash
pytest -q tests/api/test_branding_api.py tests/headers/test_engine.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```
