# ACCEPTANCE_SCENARIOS

This document is the human-readable companion to `ACCEPTANCE_TEST_MATRIX.md`. It explains the critical production-minded scenarios the repo can verify today and where the canonical code paths live.

## 1. Tenant onboarding and baseline readiness
- Tenant bootstrap: tenancy APIs, tenant middleware, and bootstrap services.
- Verification sources: `backend/app/api/routes/tenancy.py`, `backend/app/middleware/tenant.py`, `backend/app/services/tenants/bootstrap/service.py`.

## 2. Document-core generation -> approval -> client portal
- Template/version selection, generation, branding/header resolution, apply-headers, and downstream approval/archive handoff.
- Verification sources: `backend/app/api/routes/documents.py`, `backend/app/modules/templates/`, `backend/app/modules/branding/`, `backend/app/modules/headers/`, `backend/app/modules/pipelines/`, `backend/app/modules/client_portal/`.

## 3. Workflow / notifications / deadlines
- Task/deadline surfaces, unread notifications, template-based notifications, and cross-entity calendar events.
- Verification sources: `backend/app/modules/workflow/`, `backend/app/api/routes/notifications.py`, `backend/app/modules/notifications/service.py`, `backend/app/models/notifications.py`.
- Contract note: notification query validation is acceptance-relevant because invalid enum values, malformed cursors, and unsupported calendar sources must fail with the canonical structured-error payload rather than a generic 500.

## 4. Training assignment / due dates / reminders
- Training plans and due-date visibility through notifications/calendar.
- Verification sources: `backend/app/api/routes/training.py`, `backend/app/api/routes/training_next.py`, `backend/app/modules/briefings/services.py`, `docs/TRAINING_AND_LMS.md`.

## 5. Risks, incidents, inspections, prescriptions
- Incident/inspection/prescription lifecycle evidence and their relation to broader safety/risk posture.
- Verification sources: `backend/app/api/routes/incidents.py`, `backend/app/api/routes/inspections.py`, `backend/app/api/routes/prescriptions.py`, `backend/app/api/routes/risk.py`.

## 6. CRM / billing / limits
- Contract/order/invoice state consistency and billing enforcement.
- Verification sources: `backend/app/api/routes/contracts.py`, `backend/app/api/routes/orders.py`, `backend/app/api/routes/invoices.py`, `backend/app/api/routes/billing.py`, `backend/tests/test_billing_enforcement.py`.

## 7. Integrations / webhooks / observability
- Outbox/webhook reliability, API tokens, and readiness/metrics foundations.
- Verification sources: `backend/app/api/routes/webhooks.py`, `backend/app/api/routes/api_tokens.py`, `backend/app/services/outbox.py`, `backend/app/middleware/observability.py`.

## Acceptance posture
- **Production-ready enough for continued hardening:** document core, branding, notifications foundation, billing enforcement, core tenancy/security constraints.
- **Partial but coherent:** training/LMS, risk engine, advanced workflow escalation/delegation, broader EDO/provider integrations.
- **Do not overclaim:** several modules are foundations with real code and migrations, but still need more acceptance-grade scenarios before full TZ closure.
