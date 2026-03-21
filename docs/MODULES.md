# MODULES

## Canonical document-core modules
- `app.modules.branding`
- `app.modules.headers`
- `app.modules.templates`
- `app.modules.pdf`
- `app.modules.pipelines`
- `app.modules.client_portal`
- `app.modules.workflow`

## Frontend counterparts
- `src/api/branding.ts`
- `src/pages/branding/BrandingSettingsPage.tsx`
- `src/pages/documents/DocumentsWizardPage.tsx`
- `src/components/LayoutPresetEditor/*`

## Verification/tooling companions
- `scripts/branded_document_smoke.py`
- `tests/api/test_branding_api.py`
- `tests/headers/test_engine.py`

## Additional canonical modules hardened in this wave
- `app.modules.notifications` — notification listing, mark-read mutation, template/settings CRUD, calendar aggregation boundary, and structured validation for enum/cursor/source query inputs.
- `app.modules.training` / `app.domains.training` — training/LMS-ready foundations, still partial.
- `app.modules.risk` / `app.domains.risk` — risk engine foundations, still partial.

## Operational registry normalization
The prescriptions/findings/corrective-actions frontend modules now follow a common pattern: real tenant-scoped API -> shared async loader -> shared registry shell. This keeps working behavior intact while reducing per-page divergence.
