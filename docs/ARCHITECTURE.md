# Architecture

## Architectural style
- Modular monolith.
- FastAPI routers + application/domain services.
- Tenant-aware guards with RBAC/ABAC.
- Heavy document stages run asynchronously through Celery-compatible jobs.
- Document core keeps reproducibility metadata and version-aware preset selection.

## Canonical implementation paths
- API factory: `backend/app/api/app.py`
- API composition: `backend/app/api/v1/router.py`
- Branding orchestration: `backend/app/modules/branding/service.py`
- Branding API: `backend/app/modules/branding/api.py`
- Header/footer engine: `backend/app/modules/headers/engine.py`
- Layout preset API: `backend/app/modules/headers/api.py`
- Frontend branding UI: `frontend/src/pages/branding/BrandingSettingsPage.tsx`
- Frontend preset editor: `frontend/src/components/LayoutPresetEditor/LayoutPresetEditor.tsx`
- Frontend document wizard: `frontend/src/pages/documents/DocumentsWizardPage.tsx`

## Document-core flow
`Template -> branding profile -> layout preset -> header/footer render -> replace -> PDF -> approval/sign/archive`

## Branding inheritance
Effective branding is resolved in this order:
1. `Tenant.settings.branding`
2. `Company.branding_payload`
3. `Site.branding_payload`

The resolved profile contains:
- organization requisites and contacts;
- image references (`logo_file_id`, `stamp_file_id`, `signature_file_id`);
- preferred letterhead preset;
- watermark settings;
- metadata/signatories;
- reproducibility passport for preview/debug.

## Structural audit conclusions
- Backend root is `backend/` and active Python runtime starts at `backend/app/main.py`.
- Frontend root is `frontend/` and the only active JS manifest is `frontend/package.json`.
- Branding and header/footer features are canonical in `backend/app/modules/branding` and `backend/app/modules/headers`; they should not be reimplemented elsewhere.
- Historical docs exist, but the canonical docs for next tasks are the files linked from the root `README.md`.
