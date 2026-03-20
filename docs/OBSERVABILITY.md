# OBSERVABILITY

## Purpose
Canonical observability reference for the modular monolith: health/readiness probes, metrics, logging, tracing hooks, and operational smoke checks.

## Backend observability foundations
- **Application factory:** `backend/app/api/app.py`
- **Observability middleware:** `backend/app/middleware/observability.py`
- **Metrics renderer:** `backend/app/core/metrics.py`
- **Logging bootstrap:** `backend/app/core/logging.py`
- **Tracing helpers:** `backend/app/core/tracing.py`
- **Health/readiness routes:** `backend/app/api/routes/health.py`

## Runtime signals
- `/health` and related readiness probes expose service liveness and dependency checks.
- `/metrics` is registered only when metrics are enabled in settings.
- Request-level observability is layered via middleware rather than individual routers.
- Structured logging is bootstrapped from `backend/app/main.py` before the FastAPI app starts.

## Async/worker visibility
- Celery worker bootstrap: `backend/app/worker.py`
- Async pipeline and outbox flows are covered by targeted tests and smoke commands listed in `README.md` and `ACCEPTANCE_TEST_MATRIX.md`.
- Job transparency is expected through persisted run/task state rather than ephemeral in-memory progress only.

## Canonical operator commands
```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
celery -A backend.app.worker worker --loglevel=info
python scripts/repo_audit.py
PYTHONPATH=backend python scripts/branded_document_smoke.py
./scripts/smoke.sh
```

## Current limitations
- Full distributed tracing/export is still a foundation rather than a completed enterprise telemetry rollout.
- Metrics depend on environment configuration and optional infrastructure (for example Redis-backed counters and scrape wiring).
- Frontend RUM/browser telemetry is not yet a first-class subsystem in the repository.
