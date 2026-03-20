# SETUP

## Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic -c backend/app/migrations/alembic.ini upgrade head
uvicorn backend.app.main:app --reload
```

## Frontend
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

## Verification
```bash
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## Branding-first smoke path
1. Create company and optional site.
2. Create layout preset.
3. Open `/documents/branding`, maintain requisites and watermark.
4. Open `/documents/wizard`, step 5, select organization/site/preset.
5. Run branded preview and verify reproducibility snapshot.
