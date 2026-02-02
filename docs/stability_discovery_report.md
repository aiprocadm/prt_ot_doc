# Stability Discovery Report (Stage 0)

## Scope & method
Discovery is based on repository inspection only. No runtime commands were executed in this pass; failures are inferred only from documented run paths and configuration defaults.

## Repository layout (high-level)
- **Backend**: `backend/app` (FastAPI, domain services, Alembic, Celery).
- **Frontend**: `frontend/` (Vite + React SPA).
- **Infrastructure**: `docker-compose.yml`, `infra/`, `proxy/`.
- **Docs**: `docs/` (architecture, spec, runbook, compliance).

## Entrypoints
- **API**: `backend/app/main.py` creates the FastAPI app and defines a `run()` helper for Uvicorn. App import path: `app.main:app`.
- **Worker**: `backend/app/worker.py` bootstraps worker configuration; Celery worker execution is defined in `docker-compose.yml` commands.
- **Frontend**: `frontend/package.json` defines `npm run dev` for Vite.

## Tech stack
- **Backend**: FastAPI + SQLAlchemy + Alembic + Celery + Redis + MinIO/S3 + Prometheus client (see `pyproject.toml`).
- **Frontend**: React 18 + Vite + TypeScript + Zustand + React Router (see `frontend/package.json`).

## Dependencies
### Python
Declared in `pyproject.toml` and `requirements*.txt`; core dependencies include FastAPI, SQLAlchemy, Alembic, Celery, Redis, MinIO client, and aiosqlite for dockerless mode.

### Node
Frontend uses Node 20 (devcontainer) and Vite/React toolchain with Vitest and ESLint/Prettier.

## Infrastructure dependencies (docker mode)
Docker Compose provisions:
- **PostgreSQL** (`db`)
- **Redis** (`redis`)
- **MinIO** (`minio` + `minio-setup`)
- **LibreOffice** (`libreoffice`)
- **ClamAV** (`clamav`)
- **Backend/Workers/Frontend/Proxy** services

## Devcontainer / Codespaces
- `.devcontainer/devcontainer.json` uses Docker Compose with a dedicated `devcontainer` service and runs `.devcontainer/post-create.sh` to install Poetry and frontend dependencies.
- Dockerless defaults are applied by `scripts/configure_dockerless_env.sh` and `scripts/dockerless_env.sh`.

## Canonical run commands (as documented)
- **Dockerless**: `make dev:lite` (backend + frontend, SQLite + local storage) and `make test:lite`.
- **Docker**: `make dev` and `make test`.
- **Manual**: `uvicorn app.main:app` for backend, `npm run dev` for frontend.

## Current launch blockers (based on repo inspection)
- **Docker**: requires Docker daemon/CLI and the services listed above; if Docker is unavailable, `make dev` will not work and `make dev:lite` is required.
- **Dockerless**: requires Python 3.12 + Node 20 installed locally; dependency install is handled by `scripts/dev_lite.sh`.

## Gaps & next verification steps
- Execute `make dev:lite` in a clean Codespaces environment to validate end-to-end startup.
- Run `pytest --collect-only` and `make test:lite` to confirm test discovery and dockerless test stability.
