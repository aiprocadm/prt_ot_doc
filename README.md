# PRT OT DOC

Production-minded modular monolith for B2B OT / ПБ / Промбез / экология / документооборот / ЭДО / client portal scenarios.

## Canonical repository layout
- `backend/` — FastAPI application, domain/application/infrastructure split, Alembic, Celery tasks.
- `frontend/` — React 18 + TypeScript + Vite application. Canonical frontend root and the only active `package.json` live here.
- `docs/` — canonical in-repo documentation for architecture, setup, document core and audit artifacts.
- `scripts/` — bootstrap, smoke and maintenance scripts.

## Verified entrypoints
- Backend app: `backend/app/main.py` (`app` + `run()`).
- FastAPI factory: `backend/app/api/app.py`.
- Frontend app root: `frontend/src/main.tsx`.
- Vite config: `frontend/vite.config.ts`.
- Alembic config: `backend/app/migrations/alembic.ini`.

## Local setup
### Backend
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm ci
npm run dev
```

## Core commands
```bash
# backend
pytest -q
alembic -c backend/app/migrations/alembic.ini upgrade head
python -m backend.app.main

# frontend
npm --prefix frontend run dev
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run test
```

## Branded document flow
1. Create/update company card in `/api/v1/companies`.
2. Configure branding profile in `/api/v1/branding/profile/{company_id}` or UI `/documents/branding`.
3. Create layout preset in `/api/v1/layout-presets`.
4. Preview merged brand + preset via `/api/v1/branding/preview`.
5. Apply header/footer preset to a DOCX version through `/api/v1/documents/{document_version_id}/apply-headers`.
6. Continue through replace → PDF → approval/sign/archive pipeline.

## Documentation index
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
