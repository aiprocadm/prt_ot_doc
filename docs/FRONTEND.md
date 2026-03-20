# FRONTEND

## Canonical frontend root
`frontend/`

## Core runtime files
- `package.json`
- `vite.config.ts`
- `src/main.tsx`
- `src/router/AppRouter.tsx`

## Document-core screens
- `/documents/branding` — organization/site branding settings, preview history, reproducibility snapshot.
- `/documents/wizard` — step-based wizard for template selection, batch generation and branded preview before generation.
- `/admin/layout-presets` — CRUD/editor for layout presets.

## Branding UX in this wave
Wizard step 5 now supports:
- selecting organization and optional branch/site;
- selecting layout preset or using profile default;
- running live branded preview via backend branding API;
- showing the effective source chain and branch-level branded name that will be injected into headers;
- reading reproducibility metadata before generation;
- retaining short preview history in UI state.

Branding settings now expose separate `Header requisites` and `Footer requisites` fields, matching the backend profile shape used by the document core.
