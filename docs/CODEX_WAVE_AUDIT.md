# CODEX Wave Audit

_Date:_ 2026-03-21

## Canonical backend/frontend roots
- Backend API/bootstrap roots: `backend/app/main.py`, `backend/app/api/app.py`, `backend/app/api/v1/router.py`, `backend/app/api/v1/route_groups.py`.
- Backend module roots: `backend/app/api/routes`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/schemas`.
- Frontend roots: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/router/AppRouter.tsx`, `frontend/src/router/routeGroups.tsx`, `frontend/src/pages`, `frontend/src/api`, `frontend/src/hooks`.

## Active entrypoints
- ASGI app: `backend/app/main.py` -> `backend/app/api/app.py`.
- Worker: `backend/app/worker.py`.
- Browser app: `frontend/src/main.tsx` -> `frontend/src/App.tsx`.
- Router shell: `frontend/src/router/AppRouter.tsx` with permission-aware decomposition in `frontend/src/router/routeGroups.tsx`.

## Backend route map
- Platform/admin: auth, tenancy, audit, admin RBAC/users, notifications, billing, outbox, webhooks, API tokens.
- Master data: companies, sites, persons, departments, contracts, orders, invoices, NPA, PPE, training, briefings, medical.
- Operational flows: incidents, inspections, prescriptions, tasks, obligations, dashboard, reports, PWA sync.
- Document core: documents, templates, replace, branding, headers/layouts, pdf, pipelines, packs, workflow, approvals/sign/EDO.

## Frontend route/page map
- Core routes are grouped in `frontend/src/router/routeGroups.tsx` and remain permission-aware.
- The following pages were confirmed as actively mounted and in scope this wave: contractors, reference, settings, activities, medical, fire-safety, fire-training, fire-inspections, inspection-checklists, inspection-plans, inspection-prep/packages, admin.

## Active module map
- Canonical backend registration now stays in `backend/app/api/v1/route_groups.py`; `router.py` remains compatibility composition root.
- `backend/app/models/models.py` remains the ORM mega-module, but compatibility-safe extraction continues around it.
- Frontend data access for the converted operational pages is now centralized in `frontend/src/api/operations.ts`.

## Migration heads
- No schema migration was introduced in this pass.
- Alembic head remains whatever is already present under `backend/app/migrations/versions`; this wave stayed compatibility-safe.

## Tests map
- Backend tenancy regression remains covered by `tests/test_tenant_header_required.py` and `tests/test_tenancy_enforcement.py`.
- Frontend operational conversion coverage now includes `frontend/src/__tests__/OpsPages.test.tsx` and `frontend/src/__tests__/OperationsRealPages.test.tsx`.

## Static / placeholder frontend pages map
Previously static and now switched to real data in this pass:
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

## Stub / mock / deferred backend map
Confirmed and still explicitly deferred after this wave:
- `backend/app/api/routes/ws_stub.py` -> WebSocket 501 stub.
- `backend/app/celery/tasks/document_jobs_required.py` -> stub responses remain.
- `backend/app/services/pipelines_orchestrator.py` -> partial stub step handlers remain.
- `backend/app/services/integrations/stubs.py` -> 1C/ЭДО/ФРДО/ЕИСОТ stubs remain.
- `backend/app/api/routes/approval_signing_v1.py`, `approval_orchestration.py`, `edo_workflow.py` -> stub/mock providers remain isolated as non-production adapters.
- `frontend/vite.config.ts` still has no full production-grade PWA plugin/service-worker stack.

## Factually confirmed problems and gaps vs super-TZ
- Real PWA/offline shell, queue, conflict UI, media sync lifecycle: not implemented yet.
- Universal attention center/data quality center: still partial foundations, not full persistent product layer.
- Full decomposition of `backend/app/models/models.py`: still pending due compatibility/Alembic risk.
- Approval/sign/EDO provider abstraction still relies on non-certified stub/mock providers.
- Several backend document/pipeline/background-job internals still require deeper hardening beyond this wave.

## Fat files / risky compatibility paths
- `backend/app/api/v1/router.py` remains compatibility-sensitive even after grouped extraction.
- `backend/app/models/models.py` remains the heaviest persistence risk.
- `backend/app/services/pipelines_orchestrator.py` remains bloated and partly deferred.
- `frontend/vite.config.ts` remains a PWA hardening gap.

## This wave’s concrete hardening delta
- Added real backend registry endpoint `GET /medical/exams` with tenant-aware filtering and role checks.
- Converted the targeted placeholder frontend pages to real API-backed operational views using shared async/resource hooks and permission-preserving routes.
- Added focused frontend regression coverage for the newly-converted operational pages.
