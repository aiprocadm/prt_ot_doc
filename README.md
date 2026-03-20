# PRT OT DOC

Production-minded modular monolith for B2B OT / ПБ / Промбез / экология / документооборот / ЭДО / обучение / СИЗ / риски / инциденты / CRM / billing / client portal.

## Canonical repository map
- **Backend root:** `backend/`
- **Frontend root:** `frontend/`
- **Frontend package manifest:** `frontend/package.json` (canonical and only active `package.json`)
- **Backend ASGI entrypoint:** `backend/app/main.py`
- **Backend app factory:** `backend/app/api/app.py`
- **Frontend entrypoint:** `frontend/src/main.tsx`
- **Vite config:** `frontend/vite.config.ts`
- **Alembic config:** `backend/app/migrations/alembic.ini`

## Repository audit outcome
This wave re-validated:
- backend/frontend roots and active entrypoints;
- `frontend/package.json`, Vite/TS config placement and actual frontend root;
- branded document flow around organization/site branding, letterheads, preview and reproducibility;
- wizard path for selecting organization/site/layout preset before generation;
- canonical in-repo docs so the next task can read repo state directly from code and documentation.

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

## Key commands
```bash
# backend
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
pytest -q
alembic -c backend/app/migrations/alembic.ini upgrade head
python -m backend.app.main

# frontend
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --runInBand
npm --prefix frontend run build
npm --prefix frontend run dev
```

## Branded document flow
1. Create/update organization via `/api/v1/companies`.
2. Create optional branch/site via `/api/v1/sites`.
3. Create header/footer preset via `/api/v1/layout-presets` or `/admin/layout-presets`.
4. Maintain tenant/company/site branding in `/documents/branding`.
5. Build branded preview via `/api/v1/branding/preview` to get rendered header/footer sections, resolved watermark, apply-headers payload and reproducibility metadata.
6. Use `/documents/wizard` step 5 to select organization/site/preset, preview letterhead and carry reproducibility metadata into generation payloads.
7. Apply headers to generated DOCX via `/api/v1/documents/{document_version_id}/apply-headers`, then continue to PDF / approval / archive.

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
