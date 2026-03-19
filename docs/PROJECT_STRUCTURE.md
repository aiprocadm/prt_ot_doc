# Project structure

## Roots
- Backend root: `backend/`
- Frontend root: `frontend/`
- Frontend package manifest: `frontend/package.json`
- Python project manifest: `pyproject.toml`

## Backend map
- `backend/app/api/` — FastAPI routers, dependencies, app factory.
- `backend/app/models/` — ORM entities.
- `backend/app/modules/` — modular business subsystems (`branding`, `headers`, `pdf`, `replace`, `workflow`, etc.).
- `backend/app/services/` — legacy/cross-cutting services and orchestration helpers.
- `backend/app/migrations/` — Alembic environment and revisions.
- `backend/tests/`, `tests/` — backend/integration/regression test suites.

## Frontend map
- `frontend/src/api/` — API clients.
- `frontend/src/pages/` — route-level screens.
- `frontend/src/features/` — domain widgets and stateful slices.
- `frontend/src/components/` — shared UI building blocks.
- `frontend/src/stores/` — Zustand stores.

## Audit notes
- Active frontend manifest is unique: `frontend/package.json`.
- Active backend entrypoint is `backend/app/main.py`.
- `frontend/src/stores/companies.ts` was aligned with backend `PATCH /companies/{id}` contract.
