# ARCHITECTURE_MAP

## Entry points
- Backend app factory and lifespan: `backend/app/api/app.py`.
- API bootstrap entry: `backend/app/main.py`.
- API v1 router composition: `backend/app/api/v1/router.py`.
- Frontend app/router: `frontend/src/main.tsx`, `frontend/src/router/AppRouter.tsx`.

## Tenant isolation / auth / policies
- Tenant middleware and required header enforcement: `backend/app/middleware/tenant.py`, `backend/app/core/tenant.py`.
- Auth and RBAC/ABAC dependencies: `backend/app/core/security.py`, `backend/app/api/dependencies.py`.
- Frontend tenant guard and header injection: `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/api/client.ts`.

## Audit and immutable logs
- Audit API and models: `backend/app/api/v1/audit.py`, `backend/app/models/models.py`.
- Immutability checks covered by tests: `tests/test_audit_log_immutability.py`.

## Idempotency / documents / versioning
- Idempotency core and document pipeline: `backend/app/core/idempotency.py`, `backend/app/services/pipeline.py`, `backend/app/api/v1/documents.py`.
- Template/version rules and delete guardrails: `backend/app/api/v1/router.py`, `tests/test_template_delete.py`.

## Outbox / webhooks / retries
- Outbox service and dispatcher: `backend/app/services/outbox.py`.
- Webhook routing with tenant override: `backend/app/services/webhooks.py`.
- Event coverage tests: `tests/test_outbox_dispatch.py`, `tests/test_webhooks_dispatch.py`, `tests/test_webhook_routing.py`.

## Domain contours (MVP)
- Risk: `backend/app/domains/risk/*`, `tests/test_risk_assessment_kpi5.py`.
- PPE: `backend/app/api/v1/ppe.py`, `tests/api/test_ppe_api.py`.
- Training: `backend/app/api/v1/training.py`, `tests/api/test_training_api.py`.
- Obligations/tasks: `backend/app/api/v1/obligations.py`, `backend/app/api/v1/tasks.py`, `tests/integration/test_obligation_tasks.py`.

## Infra / DevX
- Dockerless scripts: `scripts/dev_lite.sh`, `scripts/test_lite.sh`, `scripts/configure_dockerless_env.sh`.
- Devcontainer (dockerless-first): `.devcontainer/devcontainer.json`, `.devcontainer/post-create.sh`.
- CI workflow: `.github/workflows/ci.yml`.
