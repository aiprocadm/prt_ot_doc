# PRT OT DOC

Production-minded modular monolith for B2B OT / ПБ / Промбез / экология / документооборот / ЭДО / обучение / СИЗ / риски / инциденты / CRM / billing / client portal.

## Canonical roots and entrypoints
- Backend root: `backend/`
- Frontend root: `frontend/`
- Canonical frontend manifest: `frontend/package.json` (the only active `package.json` in the repo)
- Backend ASGI entrypoint: `backend/app/main.py`
- Backend app factory: `backend/app/api/app.py`
- Frontend app root: `frontend/src/main.tsx`
- Vite config: `frontend/vite.config.ts`
- Alembic config: `backend/app/migrations/alembic.ini`

## What was audited in this wave
- Repository roots, package manifest location, Python/JS entrypoints.
- Branding and letterhead pipeline for tenant/company/site inheritance.
- Header/footer engine for first/odd/even sections and watermark propagation.
- Frontend branding UI and admin layout preset editor.
- Canonical docs and run commands.

## Quick start
### Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic -c backend/app/migrations/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

### Workers
```bash
celery -A backend.app.worker worker --loglevel=info
```

## Verification commands
```bash
# backend
pytest -q
pytest -q tests/api/test_branding_api.py tests/headers/test_engine.py
alembic -c backend/app/migrations/alembic.ini upgrade head
python -m backend.app.main

# frontend
npm --prefix frontend run dev
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
```

## Branded document flow
1. Create or update a company in `/api/v1/companies`.
2. Optionally create branch/site records in `/api/v1/sites`.
3. Create a header/footer preset in `/api/v1/layout-presets` or UI `/admin/layout-presets`.
4. Open `/documents/branding`, select organization or branch scope, maintain requisites, images, palette, metadata and signatories.
5. Run test preview via `/api/v1/branding/preview` to get rendered header/footer sections plus reproducibility metadata.
6. Apply the chosen preset to a document version through `/api/v1/documents/{document_version_id}/apply-headers`.
7. Continue through replace → PDF → approval/sign/archive.

## Canonical documentation
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/SETUP.md`
- `docs/BACKEND.md`
- `docs/FRONTEND.md`
- `docs/DOCUMENT_CORE.md`
- `docs/BRANDING_AND_LETTERHEADS.md`
- `docs/API_OVERVIEW.md`
- `docs/MODULES.md`
- `docs/audit/TZ_COVERAGE_MATRIX.md`
- `GAP_REPORT.md`
- `KNOWN_LIMITATIONS.md`
- `RELEASE_READINESS.md`
