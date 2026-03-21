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
3. Effective branch display name, header requisites, footer requisites, watermark, and preset are resolved into a stable header context.
4. Layout preset resolved and placeholders rendered.
5. Preview returns reproducibility metadata and `apply_headers_payload`.
6. Generated DOCX can be passed to async header application.
7. Downstream PDF/approval/archive continues through document and pipeline modules.

## Frontend architecture
- `src/api/` for server contracts.
- `src/pages/branding` for brand profile management.
- `src/pages/documents` for generation wizard.
- `src/stores/` for persisted wizard state and tenant context.

## 2026-03-21 audit-driven adjustments
- Notifications are now split into transport (`backend/app/api/routes/notifications.py`) and application logic (`backend/app/modules/notifications/service.py` + `schemas.py`).
- This wave specifically targeted a fat-router defect in notifications and converted it into a thinner API boundary without changing endpoint paths.
- Training and risk remain coherent domain foundations, but docs now classify them explicitly as partial/extension-ready rather than fully closed product areas.

## 2026-03-21 architecture decisions (current wave)
- The v1 router now uses grouped registrations from `backend/app/api/v1/route_groups.py`, which reduces composition sprawl without changing public API paths.
- Progressive model decomposition now starts through narrow compatibility modules (`backend/app/models/tenanting.py`, `backend/app/models/ppe_registry.py`) instead of direct risky extraction of SQLAlchemy declarations from `backend/app/models/models.py`.
- Operational frontend pages should prefer real tenant-scoped backend projections over showcase arrays; this wave applied that pattern to PPE, Warehouse, Prescriptions, and Audit Prep.

## 2026-03-21 incremental hardening note
The platform now uses two explicit compatibility seams for staged decomposition without contract breakage:
- `backend/app/api/v1/route_groups.py` for router topology.
- `backend/app/models/document_core.py` and `backend/app/models/tenanting.py` for progressive ORM imports away from `app.models.models`.
On the frontend, operational registries are converging on shared hooks + `RegistryTable` instead of bespoke page-local fetch/search state.
