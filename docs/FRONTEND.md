# Frontend

## Canonical frontend root
`frontend/`

## Active configuration
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`

## Key screens for this wave
- `/documents/branding` — organization/branch branding, requisites, images, palette, metadata, signatories, preview history.
- `/admin/layout-presets` — header/footer preset list and editor.
- `/documents/wizard` — document generation wizard.

## Frontend changes in this wave
- Branding screen now supports company and site scope selection.
- Branding screen consumes real backend flows for profile read/update and preview.
- Branding preview now shows resolved watermark and reproducibility passport.
- Added lightweight preview history on the page for fast operator checks.
- Layout preset editor can load existing presets and edit first/odd/even header/footer sections.

## Canonical frontend API clients
- `frontend/src/api/branding.ts`
- `frontend/src/api/documents.ts`
- `frontend/src/api/files.ts`
- `frontend/src/api/pipelines.ts`
