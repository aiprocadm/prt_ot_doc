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
- **No nested project copy:** не распаковывайте архив второй раз внутрь репозитория — каталог `prt_ot_doc-main/` в корне игнорируется и не является частью сборки (см. `.gitignore`).

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

Cross-platform direct launcher (Windows/macOS/Linux):
```bash
python scripts/dev_lite.py
```

Windows PowerShell wrapper:
```powershell
./scripts/dev_lite.ps1
```

Unix shell wrapper:
```bash
./scripts/dev_lite.sh
```

Preflight only (versions + PATH diagnostics, no start):
```bash
python scripts/dev_lite.py --preflight-only
```

Auto-free busy dev ports (`8000`, `5173`) before start:
```bash
python scripts/dev_lite.py --auto-kill-ports
```

Note for WSL: dependencies must be installed inside the selected Linux distro as well (`python`, `node`, `npm` in WSL PATH).

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

Windows note: dependency pins in `requirements.txt` are split by Python version for `asyncpg`, so Python 3.12 and 3.13 install paths remain deterministic.

### Manual frontend start
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

### Workers
Из корня репозитория задайте `PYTHONPATH=backend` (как в Docker-образе и `pyproject.toml`). Приложение Celery экспортируется из `app.services.celery_app`, а не из `backend.app.worker` (там только bootstrap `run()`).

```bash
# Windows PowerShell
$env:PYTHONPATH="backend"
celery -A app.services.celery_app:celery_app worker --loglevel=info -Q default,pdf

# Unix
export PYTHONPATH=backend
celery -A app.services.celery_app:celery_app worker --loglevel=info -Q default,pdf
```

### CLI
```bash
./ptd --help
```

## Verification commands
Canonical testing strategy, CI mapping, and merge gates: `docs/TESTING.md`.

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
- [docs/spec/TZ_FULL_UNIFIED.md](docs/spec/TZ_FULL_UNIFIED.md) — единое полное ТЗ (объём продукта, P0/P1, теги [MVP], критерии приёмки)
- [docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md](docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md) — продуктовый upgrade-spec / vNext (дорожная карта, критерии, ограничения на доработки, в т.ч. разд. 36)
- [docs/spec/README.md](docs/spec/README.md) — хаб ТЗ в `docs/spec` (приоритет `TZ_FULL` vs vNext, схема файлов, навигация)
- [RELEASE_READINESS.md](RELEASE_READINESS.md) — **готовность к релизу** (вердикт, RC-критерии; каноника блокеров: [`docs/stabilization/RELEASE_BLOCKERS_STATUS.md`](docs/stabilization/RELEASE_BLOCKERS_STATUS.md); **порядок обновления вердикта** — раздел *How to update the release verdict* в `RELEASE_READINESS.md`, ссылки в README при смене вердикта не требуют правок)
- `docs/AI_AGENT_WORKFLOW.md` — компактный цикл для AI/агентов (сначала README, ТЗ, отчёт `AI_IMPLEMENTATION_REPORT.md`, кандидаты на чистку доков)
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
