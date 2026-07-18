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

### Health / Readiness endpoints

| Path | Alias | Behaviour |
|---|---|---|
| `GET /healthz` | alias → `/health` | Процессный liveness: возвращает `{"status":"ok"}` с HTTP 200, если процесс жив. |
| `GET /health` | каноническое имя | То же, что `/healthz`. |
| `GET /readyz` | alias → `/ready` | Dependency readiness: проверяет Postgres, Redis, MinIO (обязательные), ClamAV, LibreOffice (опциональные). HTTP 200 если все обязательные OK, иначе HTTP 503 с деталями по каждому компоненту. |
| `GET /ready` | каноническое имя | То же, что `/readyz`. |

`/healthz` и `/readyz` — предпочтительные пути для Kubernetes-пробников и внешних систем мониторинга.
`/ready` возвращает JSON с полями: `status`, `postgres`, `redis`, `minio`, `clamav`, `libreoffice`, `dependencies`, `correlation_id`.

- `/metrics` is registered only when `ENABLE_METRICS=true` in settings (default: `true`).
- Request-level observability is layered via middleware rather than individual routers.
- Structured logging is bootstrapped from `backend/app/main.py` before the FastAPI app starts.

## Async/worker visibility
- Celery worker процесс: `app.services.celery_app:celery_app` (см. Docker / RUNBOOK). Файл `backend/app/worker.py` — только вызов `bootstrap("worker")`, не точка `-A` для Celery.
- Async pipeline and outbox flows are covered by targeted tests and smoke commands listed in `README.md` and `ACCEPTANCE_TEST_MATRIX.md`.
- Job transparency is expected through persisted run/task state rather than ephemeral in-memory progress only.

## Canonical operator commands
```bash
export PYTHONPATH=backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.services.celery_app:celery_app worker --loglevel=info -Q default,pdf
python scripts/repo_audit.py
python scripts/branded_document_smoke.py
./scripts/smoke.sh
```

## Current limitations
- Integration readiness diagnostics now expose provider-mode metadata so enterprise operators can see whether an adapter is a production candidate, disabled, or explicitly non-production.
- The PWA bootstrap contract now exposes user-scoped permission and conflict diagnostics, but frontend sync/conflict telemetry is still not a completed operational UI layer.
- Full distributed tracing/export is still a foundation rather than a completed enterprise telemetry rollout.
- Metrics depend on environment configuration and optional infrastructure (for example Redis-backed counters and scrape wiring).
- Frontend RUM/browser telemetry is not yet a first-class subsystem in the repository.
