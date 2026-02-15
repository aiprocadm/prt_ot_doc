# ARCHITECTURE_MAP

## Backend entrypoints
- ASGI app factory: `backend/app/api/app.py`.
- Runtime entrypoint: `backend/app/main.py`.
- API v1 composition: `backend/app/api/v1/router.py`.

## Tenant enforcement
- Middleware-level enforcement and bypass list: `backend/app/middleware/tenant.py`.
- Tenant normalization/validation + `tenant_required`: `backend/app/core/tenant.py`.
- Frontend request guard + `X-Tenant` injection: `frontend/src/api/client.ts`.

## Auth / RBAC / ABAC
- Security dependencies and token checks: `backend/app/core/security.py`, `backend/app/api/dependencies.py`.

## Audit
- Audit service/logging: `backend/app/services/audit.py`.
- Immutability verified by: `tests/test_audit_log_immutability.py`.

## Documents / idempotency / templates
- Document APIs: `backend/app/api/routes/documents.py`.
- Idempotency service: `backend/app/services/idempotency.py`.
- Template delete guards and version constraints: `tests/test_template_delete.py` + model constraints.

## Outbox / dispatcher / webhooks
- Outbox processor with retries + dead-letter: `backend/app/services/outbox.py`.
- Webhook routing (global + tenant override): `backend/app/services/webhooks.py`.
- Dispatch/routing tests: `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py`.

## Domain modules touched by KPI
- Risks: `backend/app/services/risk.py`, `tests/test_risk_assessment_kpi5.py`.
- PPE: `backend/app/api/routes/ppe.py`, `tests/api/test_ppe_events.py`.
- Training: `backend/app/api/routes/training.py`, `tests/api/test_training_api.py`.
- Tasks/obligations: `backend/app/services/tasks.py`, `backend/app/services/obligations.py`.

## DevX / Infra
- Codespaces scripts: `scripts/dev_lite.sh`, `scripts/test_lite.sh`, `scripts/configure_dockerless_env.sh`.
- Canonical commands: `make cs:dev`, `make cs:test`, `make cs:reset`.
- Devcontainer: `.devcontainer/devcontainer.json`, `.devcontainer/post-create.sh`.
- CI: `.github/workflows/ci.yml`.
