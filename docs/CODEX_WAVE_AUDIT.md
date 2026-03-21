# CODEX Wave Audit

_Date:_ 2026-03-21

## Canonical entrypoints
- Backend app bootstrap: `backend/app/api/app.py` mounts health, websocket stub, and v1 API routers.
- Main v1 API aggregation still centers on `backend/app/api/v1/router.py` and remains a compatibility hotspot.
- Frontend app bootstrap: `frontend/src/App.tsx` -> `frontend/src/router/AppRouter.tsx`.

## Active roots
- Backend active roots: `backend/app/api`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/schemas`.
- Frontend active roots: `frontend/src/pages`, `frontend/src/components`, `frontend/src/api`, `frontend/src/stores`, `frontend/src/router`.

## Migration baseline
- The repository contains Alembic migrations under `backend/app/migrations/versions`.
- This pass did not mutate the schema; migration head discovery remains a follow-up verification item for the next broader wave.

## Fat files requiring decomposition
- `backend/app/api/v1/router.py` (~1516 LOC): route registration + document/template endpoints + pipeline execution entrypoints.
- `backend/app/models/models.py` (~2980 LOC): multi-domain model concentration and compatibility risk.
- `backend/app/services/pipelines_orchestrator.py` (~834 LOC): orchestration surface still broad.
- `frontend/src/router/AppRouter.tsx` (~261 LOC): central route map remains workable but dense.

## Stub / mock / deferred map
- WebSocket remains explicitly deferred: `backend/app/api/routes/ws_stub.py` returns HTTP 501.
- Required Celery document jobs still expose stub-style responses in `backend/app/celery/tasks/document_jobs_required.py`.
- Integration adapters for 1C / EDO / FRDO / EISOT still include explicit stub and disabled implementations in `backend/app/services/integrations/stubs.py`.

## Risky compatibility areas
- `backend/app/api/v1/router.py` should be decomposed only via compatibility `include_router` extraction, not contract-breaking moves.
- `backend/app/models/models.py` requires staged compatibility imports to avoid breaking Alembic, imports, and runtime assumptions.
- Duplicate documentation trees (`docs/ADR` and `docs/adr`) should be canonicalized carefully with redirects/migration notes.
- Module naming drift such as `modules/approval` vs `modules/approvals` needs explicit canonicalization rules before cleanup.

## Frontend route and placeholder baseline
- The route shell is broad and permission-aware, but several pages still appear foundation-level or placeholder-oriented.
- Confirmed static/demo page before this pass: `frontend/src/pages/crm-finance/CrmFinancePage.tsx` used a hardcoded deals array with no API flow.
- Confirmed likely placeholder/foundation candidates for the next pass include `warehouse`, parts of dashboard variants, inspection prep, audit prep, some fire safety screens, some reference/settings views, and additional registry pages already flagged in existing repo docs.

## Incomplete super-TZ areas still visible from code
- Realtime remains deferred; REST is the current supported path.
- PWA/offline is foundational but not production-grade; no evidence in this pass of full frontend PWA packaging/mature offline queueing.
- Enterprise workflow/approval/sign/EDO maturity still requires deeper SLA/timer/orchestration hardening.
- Integration adapters remain mostly contract/stub level.
- Data quality, universal attention center, and dependency/readiness graphing need broader cross-module implementation.

## Acceptance / test baseline
- Existing repository already contains substantial backend and frontend tests.
- This pass adds focused coverage for the CRM/Finance page migration from static to real API-backed data.

## Implemented in this wave
- Replaced the `CRM / Финансы` frontend placeholder table with real tenant-scoped data assembled from existing `/contracts`, `/orders`, `/invoices`, and `/billing/plan` endpoints.
- Added explicit frontend API wrapper and page-level loading/error/empty/search states.
