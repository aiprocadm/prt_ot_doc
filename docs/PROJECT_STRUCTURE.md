# Project structure

## Canonical roots
- `backend/` — backend root.
- `frontend/` — frontend root.
- `docs/` — canonical in-repo documentation.
- `scripts/` — utility and smoke scripts.
- `pyproject.toml` — Python tooling configuration.
- `frontend/package.json` — frontend package manager entrypoint.

## Backend layout
- `backend/app/api/` — app factory, dependencies, routers, HTTP error handling.
- `backend/app/modules/` — canonical business modules (`branding`, `headers`, `pdf`, `replace`, `workflow`, `files`, `packs`, `search`, etc.).
- `backend/app/models/` — ORM models.
- `backend/app/services/` — cross-cutting services and orchestration used by legacy/bridging flows.
- `backend/app/domains/` — domain logic/helpers.
- `backend/app/migrations/` — Alembic env and migrations.

## Frontend layout
- `frontend/src/api/` — API clients.
- `frontend/src/pages/` — route-level pages.
- `frontend/src/components/` — reusable UI blocks.
- `frontend/src/features/` — feature widgets.
- `frontend/src/stores/` — Zustand stores.
- `frontend/src/router/` — route map / access control.

## Audit notes from this wave
- `frontend/package.json` is present and correct in the actual frontend root.
- No alternate frontend root was activated; top-level repo has no competing active `package.json`.
- Branding editor now supports company and site scope in the same screen instead of being company-only.
- Layout preset editor remains under `/admin/layout-presets` and is now list/edit capable, which makes it the canonical preset maintenance UI.
