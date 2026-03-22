# CODEX Wave Audit

_Date:_ 2026-03-22

## Scope of this audit wave
- Performed a factual repository audit before changing code.
- Kept changes incremental and backward-compatible.
- Focused this wave on safe decomposition of approval/EDO/sign models plus replacing legacy document-job step stubs with real orchestrator execution bridges.

## Canonical backend/frontend roots
- Backend app bootstrap: `backend/app/main.py`, `backend/app/api/app.py`.
- Backend API composition: `backend/app/api/v1/router.py`, `backend/app/api/v1/route_groups.py`.
- Backend business roots: `backend/app/api/routes`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/celery/tasks`.
- Frontend app bootstrap: `frontend/src/main.tsx`, `frontend/src/App.tsx`.
- Frontend route/page roots: `frontend/src/router/AppRouter.tsx`, `frontend/src/router/routeGroups.tsx`, `frontend/src/pages`, `frontend/src/api`, `frontend/src/stores`.

## Active entrypoints
- ASGI app: `backend/app/api/app.py`.
- API v1 compatibility composition root: `backend/app/api/v1/router.py`.
- API v1 grouped registry: `backend/app/api/v1/route_groups.py`.
- Worker/task entrypoints: `backend/app/worker.py`, `backend/app/tasks.py`, `backend/app/celery/tasks/*`.
- Frontend SPA: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> router.

## Backend route map
- Public: auth + client portal public endpoints.
- Compliance/admin: audit, admin users/authz, attestations, notifications, departments, contracts, dashboard, orders, invoices, NPA, PPE, medical, journals, risk, sites, companies, persons, training, briefings, calendar, compliance, billing.
- Operations: files, packs, incidents, inspections, prescriptions, safety ops, obligations, jobs, tasks, tenancy, outbox admin, webhooks, integrations, tenants, PWA sync, external registry, reports.
- Document core: documents, EDO workflow, approval/signing v1, approval orchestration, replace, headers, branding, pipelines, workflow, PDF, packs v2, search, analytics, export center.
- Platform extensions: client portal v1/internal, public APIs, API tokens.

## Frontend route/page map
- Enterprise screens exist for dashboards, documents, templates, packs/jobs, approvals/EDO, incidents, inspections, training, PPE, warehouse, admin, client portal, CRM/finance, files, search, audit, branding, integrations, calendar.
- Router-level permission awareness is implemented through route grouping plus ability checks, but not every page has equally mature action-level hiding and empty/loading/error consistency.

## Active module map
- API route grouping is now explicitly described by `ROUTER_GROUP_ORDER`, `ROUTER_GROUPS`, and `describe_router_groups()` in `backend/app/api/v1/route_groups.py`.
- ORM decomposition is partial: focused modules already exist (`document.py`, `document_core.py`, `tenanting.py`, `safety_core.py`, `risk.py`), and this wave extracted approval/EDO/sign primitives into `backend/app/models/approval_workflow.py` while keeping `backend/app/models/models.py` as the compatibility mega-module.
- Document pipeline orchestration spans `backend/app/services/pipelines_orchestrator.py`, `backend/app/tasks.py`, `backend/app/celery/tasks/job_steps.py`, and `backend/app/celery/tasks/document_jobs_required.py`.
- Frontend operational projections are largely aggregated through `frontend/src/api/operations.ts` and page-level hooks.

## Migration heads
- No migration changes in this wave.
- Existing Alembic history remains authoritative under `backend/app/migrations/versions` if present in the deployment context.
- This wave intentionally avoided schema changes.

## Tests map
- Backend tests cover tenanting, authz, billing, audit, pipeline orchestration, search, client portal, incidents/inspections/CAPA, workflow notifications, files, templates, and release/webhook stubs.
- This wave adds focused regression coverage for document-job compatibility wrappers and route-group description metadata.
- Frontend code has real-data pages for multiple formerly static screens, but this wave did not change runtime UI behavior.

## Static / placeholder frontend pages map
Factually confirmed as already moved from static foundations to real data flows:
- `frontend/src/pages/contractors/ContractorsPage.tsx`
- `frontend/src/pages/reference/ReferencePage.tsx`
- `frontend/src/pages/settings/SettingsPage.tsx`
- `frontend/src/pages/activities/ActivitiesPage.tsx`
- `frontend/src/pages/medical/MedicalPage.tsx`
- `frontend/src/pages/fire-safety/FireSafetyPage.tsx`
- `frontend/src/pages/fire-training/FireTrainingPage.tsx`
- `frontend/src/pages/fire-inspections/FireInspectionsPage.tsx`
- `frontend/src/pages/inspection-checklists/InspectionChecklistsPage.tsx`
- `frontend/src/pages/inspection-plans/InspectionPlansPage.tsx`
- `frontend/src/pages/inspection-prep/InspectionPrepPackagesPage.tsx`
- `frontend/src/pages/admin/AdminPage.tsx`

Still remaining as broader gaps vs super-TZ:
- full PWA plugin + service worker + offline queue/conflict UI,
- stronger attention center and data quality center UX,
- deeper role-based dashboard projections,
- richer client/external operational history/request flows.

## Stub / mock / deferred backend map
Confirmed problems and current state:
- `backend/app/api/routes/ws_stub.py` -> WebSocket 501 stub remains deferred.
- `backend/app/celery/tasks/document_jobs_required.py` -> legacy task wrappers now execute real internal orchestrator steps for render/build/sign/EDO/index flows through a tenant-aware compatibility bridge; report/integration sync wrappers remain compatibility-only envelopes.
- `backend/app/services/pipelines_orchestrator.py` -> still a fat orchestration file, but this wave extracted artifact/sign/EDO/index step handlers into `backend/app/services/pipeline_step_handlers.py` to reduce bloat without changing contracts.
- `backend/app/services/integrations/stubs.py` -> 1C/ЭДО/ФРДО/ЕИСОТ stubs remain non-production by design.
- `backend/app/api/routes/approval_signing_v1.py`, `approval_orchestration.py`, `edo_workflow.py` -> still expose mock/stub provider flows and need future production-adapter hardening.
- `frontend/vite.config.ts` -> no production-grade PWA plugin setup.

## Fat files requiring decomposition
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
- `backend/app/tasks.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `backend/app/api/routes/edo_workflow.py`

## Legacy / compatibility pairs and risky paths
- `backend/app/api/v1/router.py` vs `backend/app/api/v1/route_groups.py`.
- `backend/app/models/models.py` vs focused model modules under `backend/app/models/*`.
- `backend/app/tasks.py` vs `backend/app/celery/tasks/document_jobs_required.py`.
- Approval/EDO/sign flows are split between `approval_signing_v1.py`, `approval_orchestration.py`, and `edo_workflow.py`.
- Files/PDF/pipeline/pack routes have both legacy and canonical registration layers.

## Gaps relative to the super-TZ
### P0 still open or only partially addressed
- Full decomposition of `router.py` and `models.py` is not completed.
- Tenant/authz/audit/correlation-id consistency still needs broader endpoint-by-endpoint verification.
- Document chain centralization/readiness scoring is still incomplete.
- Tasks/timeline/attention center is not yet a universal operational layer.
- Workflow/sign/EDO provider abstraction is cleaner than before but not production-adapter complete.
- PWA hardening remains largely open.

### P1/P2 not attempted in this wave
- Data quality issue model and dashboard APIs.
- Full offline queue/conflict UX.
- End-to-end incident/inspection/prescription/CAPA closure loops beyond current v1 foundations.
- Real certified provider adapters.

## What changed in this wave
- Extracted approval/EDO/sign ORM primitives into `backend/app/models/approval_workflow.py` with compatibility imports preserved through `backend/app/models/models.py`.
- Extracted pipeline step handlers into `backend/app/services/pipeline_step_handlers.py` and wired `PipelineOrchestrator` to the focused module.
- Replaced stub-like document-job Celery wrappers with tenant-aware runtime compatibility bridges that execute real orchestrator steps for render/build/sign/EDO/index flows.
- Added regression tests covering both the step-handler dispatch path and the document-job compatibility bridge behavior.
