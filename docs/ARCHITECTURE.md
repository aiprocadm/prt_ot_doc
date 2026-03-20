# ARCHITECTURE

## Platform shape
- **Style:** modular monolith.
- **Backend:** FastAPI + SQLAlchemy 2.x + Alembic + Celery.
- **Frontend:** React + TypeScript + Vite.
- **Key cross-cutting concerns:** tenancy, RBAC/ABAC, audit, idempotency, async jobs, structured errors.

## Canonical backend layering
- `api/` — HTTP composition and route contracts.
- `modules/` — product modules and bounded contexts.
- `services/` — orchestration/use-case logic.
- `models/`, `schemas/`, `db/` — persistence and contracts.

## Document core architecture
1. Template/version selected.
2. Branding profile resolved via tenant/company/site inheritance.
3. Layout preset resolved and placeholders rendered.
4. Preview returns reproducibility metadata and `apply_headers_payload`.
5. Generated DOCX can be passed to async header application.
6. Downstream PDF/approval/archive continues through document and pipeline modules.

## Frontend architecture
- `src/api/` for server contracts.
- `src/pages/branding` for brand profile management.
- `src/pages/documents` for generation wizard.
- `src/stores/` for persisted wizard state and tenant context.
