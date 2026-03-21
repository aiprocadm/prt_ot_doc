# PRT OT DOC

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
