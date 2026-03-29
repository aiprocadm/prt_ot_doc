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

### Local dockerless / Codespaces
```bash
make dev-lite
```

This is the recommended local start path in this workspace. It prepares dockerless env defaults, initializes the SQLite schema, starts backend on `http://localhost:8000`, and starts frontend on `http://localhost:5173`.

Default local login:
- tenant: `demo`
- email: `admin@example.com`
- password: `admin123`

### Manual backend start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python scripts/run_backend_lite.py
```

### Manual frontend start
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

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
6. Use the returned `apply_headers_payload` to run `/api/v1/documents/{document_version_id}/apply-headers`.
7. Continue into PDF / approval / archive flows.

### What is now production-minded in the branded flow
- tenant → company → site inheritance for requisites and images;
- branch-level branded display name now flows into the preview/apply-headers context, so overridden `branch_label` is reflected in generated headers instead of the raw site name;
- explicit `header_details` and `footer_details` are available in the branding profile for stable letterhead requisites on firm blanks;
- preset-source diagnostics and scope chain in preview responses;
- stable reproducibility metadata, including branding payload hash, header context hash, rendered section hash, and preset content hash;
- wizard preview history persisted in the wizard store for operator continuity;
- merge-safe branding updates that do not erase existing requisites, metadata, logos, or stamps during partial edits.
B2B multi-tenant SaaS платформа для ОТ / ПБ / ПромБез / экологии / обучения / ЭДО / документов. Repo должен быть self-explanatory для следующей волны без опоры на память prompt.

## Canonical entrypoints
- Backend app factory: `backend/app/api/app.py`
- Backend main: `backend/app/main.py`
- Frontend app: `frontend/src/App.tsx`
- Frontend router: `frontend/src/router/AppRouter.tsx`
- Templates/document core API: `backend/app/api/v1/router.py`, `backend/app/api/routes/documents.py`
- Tenant/admin bootstrap: `scripts/bootstrap_tenant.py`, `backend/app/services/dev_bootstrap.py`, `backend/app/services/demo_bootstrap.py`

## What was hardened in this wave
- Template catalog API normalized around `code`, `category`, `status`, and `scope` metadata.
- Custom template version upload now correctly updates `current_version_id`.
- Document generation now resolves template by `code` or legacy `name`, reducing broken-path risk.
- Repo now contains canonical docs for demo access, owner/admin bootstrap, user role issuance, and template upload/rendering.

## Core user flow for custom templates
1. Create template card in `/templates` or `POST /api/v1/templates/catalog`.
2. Set scope: tenant / company / site(branch) / system foundation.
3. Upload DOCX version.
4. Run lint and preview.
5. Generate organization/branch-specific document through `/api/v1/documents/generate`.
6. Continue via header/footer, replace, PDF, approvals, signatures, archive.

## Canonical documentation
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/SETUP.md`
- `docs/BACKEND.md`
- `docs/FRONTEND.md`
- `docs/MODULES.md`
- `docs/API_OVERVIEW.md`
- `docs/DOMAIN_MODEL.md`
- `docs/WORKFLOWS_AND_EVENTS.md`
- `docs/DOCUMENT_CORE.md`
- `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`
- `docs/DEMO_ACCESS.md`
- `docs/OWNER_ADMIN_ACCESS.md`
- `docs/USER_ACCESS_AND_ROLES.md`
- `docs/TRAINING_AND_LMS.md`
- `docs/RISK_ENGINE.md`
- `docs/INTEGRATIONS.md`
- `docs/SECURITY.md`
- `docs/OBSERVABILITY.md`
- `docs/TESTING.md`
- `docs/audit/TZ_COVERAGE_MATRIX.md`
- `ACCEPTANCE_TEST_MATRIX.md`
- `GAP_REPORT.md`
- `RELEASE_READINESS.md`
- `KNOWN_LIMITATIONS.md`
- `CHANGELOG.md`
- `CHANGED_MODULES_AND_DECISIONS.md`

## 2026-03-21 hardening highlights
- Notifications API was refactored into `backend/app/modules/notifications/` so routers no longer own query/mutation/calendar aggregation logic.
- Invalid notification filters (`status`, `priority`, `channel`, `type`) now return structured 422 responses instead of leaking enum conversion failures.
- Notification cursor parsing and calendar `source` filtering now also fail with the same structured 422 contract instead of surfacing generic server errors for malformed values.
- Training/LMS, risk-engine, and acceptance-scenario docs were normalized to clearly distinguish implemented foundations from remaining gaps.
- Template catalog/version DTOs are now aligned with the frontend and expose canonical scope/type/current-version/version-history metadata for custom template work.
- Repo-level docs now explicitly describe demo access, owner bootstrap, and user role issuance so the next wave can rely on repository artifacts instead of branch memory.
