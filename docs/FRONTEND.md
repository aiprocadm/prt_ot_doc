# Frontend

## Canonical frontend root
`frontend/`

## Active config files
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/.eslintrc.cjs`

## Important screens
- `/documents` — document workspace.
- `/documents/wizard` — generation wizard.
- `/documents/branding` — branding profile and letterhead preview screen.
- `/admin/layout-presets` — layout preset editor.

## Contract alignment fixes in this wave
- Company updates now use `PATCH /companies/{id}` from the store.
- Added dedicated branding client in `frontend/src/api/branding.ts`.
