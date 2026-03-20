# SETUP

## Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic -c backend/app/migrations/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

## Workers
```bash
celery -A backend.app.worker worker --loglevel=info
```

## CLI
```bash
./ptd --help
```

## Verification
```bash
pytest -q tests/test_entrypoints.py
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## Branded generation smoke
1. Create company and optional site.
2. Create one layout preset in `/api/v1/layout-presets`.
3. Configure branding in `/documents/branding`.
4. Open `/documents/wizard?step=5`.
5. Select company/site/preset and run branded preview.
6. Verify rendered sections, watermark, resolution chain, and reproducibility snapshot.
7. Generate DOCX, then apply headers asynchronously through `/api/v1/documents/{document_version_id}/apply-headers`.
