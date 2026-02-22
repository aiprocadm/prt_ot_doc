# Environment bootstrap

1. Copy `.env.example` to `.env`.
2. Run `make up`.
3. Run `make smoke`.

## Services

- `api`: FastAPI on `:8000`
- `worker`: Celery worker
- `beat`: Celery beat
- `postgres`: PostgreSQL 16
- `redis`: Redis 7
- `minio`: S3-compatible storage on `:9000`
- `minio-mc`: one-shot bucket initializer
- `clamav`: antivirus daemon
- `lo`: libreoffice pool container

## Health endpoints

- `/healthz` — process liveness.
- `/readyz` — dependency readiness (postgres, redis, minio, optional clamav/libreoffice).

## Tenant smoke profile

Smoke scripts use tenant header from `TENANT_HEADER_NAME` and `DEFAULT_TENANT_SLUG` (default `demo`).
