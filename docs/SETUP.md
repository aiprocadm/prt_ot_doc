# SETUP

## Local dockerless / Codespaces
```bash
make dev-lite
```

This is the recommended local start path for this workspace. It configures dockerless env defaults, creates the SQLite schema from metadata, starts backend on `http://localhost:8000`, and starts frontend on `http://localhost:5173`.

Default local login:
- tenant: `demo`
- email: `admin@example.com`
- password: `admin123`

## Manual backend
Интерпретатор **Python 3.12** совпадает с CI (включая `ci.yml` и `e2e-smoke.yml`) и Docker-образом (`Dockerfile`); другие минорные версии могут не собрать зависимости (например `asyncpg`).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python scripts/run_backend_lite.py
```

## Manual frontend
```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

## Workers
Требуется `PYTHONPATH=backend`. Целевой объект Celery: `app.services.celery_app:celery_app` (см. `docker-compose.yml`, `docs/RUNBOOK.md`). Модуль `backend.app.worker` выполняет только `bootstrap`, не является Celery-приложением.

```bash
export PYTHONPATH=backend   # или $env:PYTHONPATH="backend" в PowerShell
celery -A app.services.celery_app:celery_app worker --loglevel=info -Q default,pdf
```

## CLI
```bash
./ptd --help
```

## Environment source of truth
- Base environment templates: `.env.example` and `backend/.env.example`
- Human-readable variable reference: `docs/ENV_REFERENCE.md`
- Multi-tenant defaults to review before first boot: `DEFAULT_TENANT_SLUG`, `ADMIN_TENANT`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- Infra/service endpoints to align with Docker or local services: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `S3_ENDPOINT`
- Document/PDF pipeline settings to review on workstation installs: `LIBREOFFICE_BIN`, `PDF_LIBREOFFICE_TIMEOUT_SECONDS`, `FONTS_PATH`

## Verification
- Corporate-readiness slice: `pytest -q backend/tests/test_pwa_sync_bootstrap.py backend/tests/test_document_jobs_required.py backend/tests/test_corporate_readiness_hardening.py`
```bash
pytest -q tests/test_entrypoints.py
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
PYTHONPATH=backend python scripts/branded_document_smoke.py
PYTHONPATH=backend python scripts/repo_audit.py  # regenerates docs/audit/REPOSITORY_AUDIT.md and docs/audit/REPOSITORY_AUDIT.json
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## Branded generation smoke
1. Create company and optional site.
2. Create one layout preset in `/api/v1/layout-presets`.
3. Configure branding in `/documents/branding`.
4. Open `/documents/wizard?step=5`.
5. Select company/site/preset and run branded preview.
6. Verify rendered sections, watermark, resolution chain, and reproducibility snapshot.
7. Generate DOCX, then apply headers asynchronously through `/api/v1/documents/{document_version_id}/apply-headers`.
8. For a repo-local smoke without bootstrapping data, run `make branded-smoke` to verify the canonical `branding -> apply_headers` path on a DOCX stub.
