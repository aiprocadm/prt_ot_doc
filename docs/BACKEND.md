# BACKEND

## Active runtime entrypoints
- ASGI: `backend/app/main.py`
- App factory: `backend/app/api/app.py`
- CLI: `backend/app/cli/main.py`
- Alembic: `backend/app/migrations/alembic.ini`
- Repo-root compatibility package: `app/__init__.py`

## Document-core related modules
- `app.modules.branding` — resolves tenant/company/site inheritance into a normalized branding profile.
- `app.modules.headers` — stores layout presets and applies headers/footers to DOCX.
- `app.api.routes.documents` — legacy and orchestrated document generation routes.
- `app.tasks.apply_headers_job` — async header application job.

## Production-minded guarantees in scope
- tenant-aware queries for company/site/preset resolution;
- idempotent header application endpoint;
- reproducibility metadata returned by branding preview;
- stable branding payload hash embedded into preview reproducibility metadata;
- explicit `header_details` / `footer_details` fields in the branding profile for firm-letterhead requisites;
- site branding can override the display branch name used by rendered headers via `branch_label`;
- merge-safe branding profile updates so partial edits do not erase existing requisites/assets;
- additive API evolution: preview now returns `apply_headers_payload` and `wizard_defaults` without breaking existing clients.
