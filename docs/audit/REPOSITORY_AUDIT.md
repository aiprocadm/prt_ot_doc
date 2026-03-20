# Repository audit snapshot

## Canonical roots
- Backend root: `backend/` (entrypoint `backend/app/main.py`).
- Frontend root: `frontend/` (active manifest `frontend/package.json`).
- Python project config: `pyproject.toml`.

## Frontend manifests found
- `frontend/package.json`

## Structural flags
- Backend entrypoint exists: **yes**.
- Frontend package.json count: **1**.
- Frontend Vite config exists: **yes**.
- Frontend tsconfig exists: **yes**.

## Legacy / compatibility paths to keep out of new code
- `docs/ADR` exists=True; `docs/adr` exists=True. Canonical path should be documented before new changes touch either tree.
- `backend/app/modules/approval` exists=True; `backend/app/modules/approvals` exists=True. Canonical path should be documented before new changes touch either tree.
