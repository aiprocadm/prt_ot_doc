# PRT OT DOC

Production-minded modular monolith for B2B охрана труда / промышленная и пожарная безопасность / экология / документооборот / ЭДО / обучение / СИЗ / риски / инциденты / CRM / billing / client portal.

## Canonical repository map
- **Backend root:** `backend/`
- **Frontend root:** `frontend/`
- **Only active frontend manifest:** `frontend/package.json`
- **Backend ASGI entrypoint:** `backend/app/main.py`
- **Backend app factory:** `backend/app/api/app.py`
- **Frontend entrypoint:** `frontend/src/main.tsx`
- **Vite config:** `frontend/vite.config.ts`
- **Alembic config:** `backend/app/migrations/alembic.ini`
- **CLI wrapper:** `./ptd`

## Structural audit summary
This wave re-audited the repository and confirmed the following canonical paths:
- backend runtime lives under `backend/app`, while repo-root `app/__init__.py` is a compatibility package for legacy `app.*` imports;
- frontend runtime lives under `frontend/`, and there is no second active `package.json` outside that root;
- branded document functionality is split canonically between `backend/app/modules/branding`, `backend/app/modules/headers`, `frontend/src/pages/branding`, and `frontend/src/pages/documents/DocumentsWizardPage.tsx`;
- document wizard preview state is now persisted in the wizard store so brand preview, resolution chain, and reproducibility snapshot survive step navigation/reloads.

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

Production build uses explicit vendor chunking in `frontend/vite.config.ts` to keep the entry bundle below the previous warning threshold and improve long-term cache behavior.

### Workers
```bash
celery -A backend.app.worker worker --loglevel=info
```

### CLI
```bash
./ptd --help
```

## Verification commands
```bash
# backend
pytest -q tests/test_entrypoints.py
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
PYTHONPATH=backend python scripts/branded_document_smoke.py
python scripts/repo_audit.py  # refreshes docs/audit/REPOSITORY_AUDIT.md + docs/audit/REPOSITORY_AUDIT.json

# frontend
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## Branded document flow
1. Create or update organization via `/api/v1/companies`.
2. Create optional branch/site via `/api/v1/sites`.
3. Create a letterhead preset via `/api/v1/layout-presets` or `/admin/layout-presets`.
4. Maintain tenant/company/site branding in `/documents/branding`.
5. Build a branded preview via `/api/v1/branding/preview` or `/documents/wizard` step 5.
6. Run single generation from `/documents/wizard` to persist server-side branded generation history in `/api/v1/branding/history`.
7. Use the returned `apply_headers_payload` to run `/api/v1/documents/{document_version_id}/apply-headers`.
8. Continue into PDF / approval / archive flows.

### What is now production-minded in the branded flow
- tenant → company → site inheritance for requisites and images;
- branch-level branded display name now flows into the preview/apply-headers context, so overridden `branch_label` is reflected in generated headers instead of the raw site name;
- explicit `header_details` and `footer_details` are available in the branding profile for stable letterhead requisites on firm blanks;
- preset-source diagnostics and scope chain in preview responses;
- stable reproducibility metadata, including branding payload hash, header context hash, rendered section hash, and preset content hash;
- wizard preview history persisted in the wizard store for operator continuity;
- merge-safe branding updates that do not erase existing requisites, metadata, logos, or stamps during partial edits.

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
- `docs/WORKFLOWS_AND_EVENTS.md`
- `docs/OBSERVABILITY.md`
- `docs/TESTING.md`
- `docs/audit/TZ_COVERAGE_MATRIX.md`
- `docs/audit/REPOSITORY_AUDIT.md`
- `docs/audit/REPOSITORY_AUDIT.json`
- `GAP_REPORT.md`
- `KNOWN_LIMITATIONS.md`
- `RELEASE_READINESS.md`
