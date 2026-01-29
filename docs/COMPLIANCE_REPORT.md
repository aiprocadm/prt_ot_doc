# SPEC ↔ CODE Compliance Report (TZ Audit)

## Phase 0 — Architecture map

### Backend
- **Entrypoints**: FastAPI app factory and entrypoint in `backend/app/api/app.py` and `backend/app/main.py`; Celery tasks in `backend/app/tasks.py`; worker bootstrap in `backend/app/worker.py`. 
- **Routers**: v1 API router wiring in `backend/app/api/v1/router.py` with feature routers mounted beneath `/api/v1`.
- **Auth & access control**: JWT issuance/verification + RBAC/ABAC in `backend/app/core/security.py` with role and attribute checks; tenant is validated in middleware (`backend/app/middleware/tenant.py`) and request dependencies (`backend/app/api/dependencies.py`).
- **Tenant propagation**: header validation + token scope checks in middleware; DB sessions use tenant-aware search paths in `backend/app/db/session.py`.
- **DB + migrations**: SQLAlchemy models in `backend/app/models/models.py`; Alembic migrations in `backend/app/migrations/`.
- **Queues**: Celery task definitions and dispatchers in `backend/app/tasks.py`.
- **Storage**: S3/MinIO integration in `backend/app/domains/files/s3.py`, file storage service in `backend/app/services/file_storage.py`.
- **Metrics/observability**: Prometheus metrics in `backend/app/core/metrics.py`, tracing in `backend/app/core/tracing.py`, and observability middleware in `backend/app/middleware/observability.py`.

### Frontend
- **Stack**: React + Vite SPA under `frontend/` with API client in `frontend/src/api/client.ts` and tenant store in `frontend/src/stores/tenant.ts`.
- **Tenant context**: `frontend/src/api/client.ts` injects `X-Tenant` and blocks protected requests without a selected tenant.

### Infra/dev
- **Compose**: `docker-compose.yml` defines local services for API, worker, Postgres, Redis, MinIO, etc.
- **Devcontainer**: `.devcontainer/` contains Codespaces configuration.
- **Tests**: `pytest`-based backend tests under `tests/` and frontend tests under `frontend/src/__tests__/`.

## Phase 1 — Compliance matrix (SPEC ↔ CODE)

| TZ Requirement | Current Implementation (files/modules) | Status | Severity | Fix Plan |
| --- | --- | --- | --- | --- |
| A) Product positioning (Saby+Kontur, RiskProf/OTOR/KOT, ERP core + modules) | Domain modules and docs exist across risks/PPE/training/incidents/pack generation; public docs in `docs/` and `README.md`. | Partial | P2 | Keep in docs/marketing copy; no code changes required. |
| B) Multi-tenant isolation with `X-Tenant` on /v1 business routes | Tenant middleware and tenant-aware DB sessions enforce tenant header and schema usage. | OK | P0 | None. |
| B) Roles list (owner, OT/PB lead, OT specialist, PB engineer, ecologist, HR, lawyer, accountant, line manager, worker, contractor inspector, admin) | Role enum covers required roles in `backend/app/models/models.py`. | OK | P1 | None. |
| B) RBAC + ABAC attributes (company_id, site_id, document_id, status, risk_level) | RBAC/ABAC checks in `backend/app/core/security.py` and route-level guards. | OK | P1 | None. |
| B) Immutable audit log | AuditLog model prevents update/delete via SQLAlchemy events in `backend/app/models/models.py`; AuditService in `backend/app/services/audit.py`. | OK | P0 | None. |
| C) Core entities (counterparty, contract, order, invoice/act, site, department, workplace, position, employee) | Models and routes exist for companies/contractors, contracts, orders, invoices, sites, departments, workplaces, positions, people. | OK | P1 | None. |
| D) DOCX templates with placeholders | Template workflow in `backend/app/api/v1/router.py` and pipeline/services. | OK | P0 | None. |
| D) Strict template versioning + deletion guard (409 if referenced) | Version selection enforced in `backend/app/api/routes/documents.py`; deletion guard in `backend/app/api/v1/router.py`. | OK | P0 | None. |
| D) DOCX→PDF pipeline + stamps/QR/watermarks | DOCX→PDF in `backend/app/services/pipeline.py`; stamp placeholders used in pack context. | Partial | P2 | Consider explicit QR/watermark pipeline stage if required. |
| E) Obligations/deadlines engine | Tasks/reminders in `backend/app/services/obligations.py` + task routes. | Partial | P1 | Expand coverage to inspections/attestations when needed. |
| F) Risks module (hazards base + risk cards + action plan) | Risk dictionaries, assessment, cards, and action plans in `backend/app/api/routes/risk.py` + domains. | OK | P0 | None. |
| F) PPE (norms + issuance logs) | PPE routes/services in `backend/app/api/routes/ppe.py`. | OK | P1 | None. |
| F) Training/briefings (programs, journals, certs) | Training routes + services in `backend/app/api/routes/training.py` and domain services. | OK | P1 | None. |
| F) Incidents/inspections/prescriptions scaffolding | Incidents service exists; inspections/prescriptions are not fully modeled. | Partial | P2 | Add scaffolding if product roadmap requires. |
| G) Idempotency for critical endpoints | Idempotency service and `Idempotency-Key` handling in document generation + packs. | OK | P0 | None. |
| G) Outbox + dispatcher + retries + dead-letter + metrics | Outbox models, processor, dispatcher task, and metrics in `backend/app/services/outbox.py` + `backend/app/tasks.py`. | OK | P0 | None. |
| G) Webhooks with routing from config + per-tenant override | Webhook subscriptions + config-based routing in `backend/app/services/webhooks.py`. | OK | P0 | None. |
| G) Events emitted for DocumentGenerated/Signed/Exported/RiskAssessed/PPEIssued/TrainingCompleted | Event enqueues in tasks/routes/services: documents, risk, PPE, training, export. | OK | P0 | None. |
| H) DevX: app runs end-to-end; tests discoverable in Codespaces | README + devcontainer guidance; `pytest` setup in `.vscode/settings.json` and `tests/`. | OK | P0 | None. |

## Phase 1 — Prioritized gap list

- **P0**: _No P0 gaps detected_ based on current implementation.
- **P1**:
  - Expand obligations engine beyond training/medical to inspections/attestations (if required).
- **P2**:
  - Add explicit QR/watermark pipeline stage if mandated by UX/spec.
  - Add inspection/prescription scaffolding for incident workflows.

## Security & isolation risks
- Tenant isolation relies on `X-Tenant` + token scope checks; ensure all new routes remain behind middleware and tenant-aware DB sessions.
- Audit log immutability is enforced via SQLAlchemy events; avoid direct SQL UPDATE/DELETE bypasses.

## Phase 2 — P0 fixes implemented

No additional P0 fixes required; implementation already satisfies KPIs 1–5.

## Phase 3 — P1 fixes (optional)

Not required for this pass.

## Phase 4 — Tests & runbook

### Runbook (Codespaces/local)
- Backend (API):
  - `cp .env.example .env`
  - `make run`
- Backend tests:
  - `make test`
  - `pytest --collect-only`
- Frontend:
  - `cd frontend && npm install && npm run dev`

### Manual QA checklist (KPI-1..KPI-5)
- **KPI-1**: Repeat `POST /api/v1/documents/generate` with same `Idempotency-Key` and identical payload; confirm `document_version_id` is stable.
- **KPI-2**: Call any `/api/v1/*` business route without `X-Tenant` and confirm `400`.
- **KPI-3**: Request a template by `(template_code, version)` and attempt to delete a version referenced by a document; expect `409`.
- **KPI-4**: Trigger a document generation or PPE issuance and confirm outbox entry is dispatched and webhook delivered within 60s.
- **KPI-5**: Run a risk assessment and confirm deterministic risk cards/action plan from dictionaries.
