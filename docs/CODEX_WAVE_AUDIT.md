# CODEX Wave Audit

_Date:_ 2026-03-22

## Scope of this audit wave
- Performed a factual repository audit before changing code.
- Kept the wave incremental and backward-compatible.
- Focused implementation on three verified hardening seams: background job compatibility wrappers, frontend PWA bootstrap, and explicit non-production provider isolation metadata for approval/sign/EDO flows.

## Canonical backend/frontend roots
- Backend bootstraps: `backend/app/main.py`, `backend/app/api/app.py`.
- Backend composition roots: `backend/app/api/v1/router.py`, `backend/app/api/v1/route_groups.py`.
- Backend domain roots: `backend/app/api/routes`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/celery/tasks`.
- Frontend bootstraps: `frontend/src/main.tsx`, `frontend/src/App.tsx`.
- Frontend routing/data roots: `frontend/src/router`, `frontend/src/pages`, `frontend/src/api`, `frontend/src/hooks`, `frontend/src/permissions`.

## Active entrypoints
- ASGI app: `backend/app/api/app.py`.
- API router composition: `backend/app/api/v1/router.py` backed by `backend/app/api/v1/route_groups.py`.
- Worker/task entrypoints: `backend/app/worker.py`, `backend/app/tasks.py`, `backend/app/celery/tasks/*`.
- Frontend SPA: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `frontend/src/router/AppRouter.tsx`.
- Frontend build/runtime shell: `frontend/vite.config.ts` plus Vite PWA runtime registration in `frontend/src/pwa/register.ts`.

## Backend route map
- `public`: auth + public client portal.
- `compliance_and_admin`: audit, admin users/authz, attestations, notifications, departments, contracts, dashboard, orders, invoices, NPA, PPE, medical, journals, risk, sites, companies, persons, training, briefings, calendar, compliance, billing.
- `operations`: files, packs, incidents, inspections, prescriptions, safety ops, obligations, jobs, tasks, tenancy, outbox admin, webhooks, integration readiness, tenants, PWA sync, external registry, reports.
- `document_core`: documents, EDO workflow, approval/signing v1, approval orchestration, replace, headers, branding, pipelines, workflow, PDF, packs v2, search, analytics, export center.
- `platform_extension`: client portal v1/internal, public API, API tokens, portal requests.
- Router grouping is factually declared in `backend/app/api/v1/route_groups.py`, while `backend/app/api/v1/router.py` remains the compatibility-heavy composition layer.

## Frontend route/page map
- Router registry is centered in `frontend/src/router/pageRegistry.tsx`, grouped by `routeGroups.tsx`, enforced by `ProtectedRoute.tsx`.
- Operational pages exist for dashboards, documents/templates/packs, approvals/EDO, incidents/inspections/CAPA, training/PPE/warehouse, admin, files/search/audit, client portal, CRM/finance, reference/settings, contractors, activities, and calendar.
- Connectivity/offline messaging exists via `frontend/src/components/common/ConnectivityBanner.tsx`, but true offline queue/conflict UX is still incomplete.

## Active module map
- Router decomposition is already partially in place via `route_groups.py`; `router.py` remains the compatibility-heavy composition file.
- ORM decomposition is partial: focused modules exist, `backend/app/models/tenanting.py` already re-exports tenant entities, and this wave adds `backend/app/models/workflow.py` as a compatibility layer for approval/sign/EDO entities while `backend/app/models/models.py` remains the large aggregator.
- Pipeline/document orchestration centers on `backend/app/services/pipelines_orchestrator.py`, `backend/app/tasks.py`, `backend/app/celery/tasks/document_jobs_required.py`, and extracted `backend/app/services/pipeline_step_handlers.py`.
- Frontend operational data flows aggregate through `frontend/src/api/*.ts` and page-level hooks such as `useAsyncResource` / `useLocalRegistry`.

## Migration heads
- Migration head files currently visible in `backend/app/migrations/versions` are topped by the `202603*` series (latest filename in this repo audit: `20260314_next62_analytics_search_export_center.py`).
- No migration changes were made in this wave; a dedicated schema consistency pass is still needed to confirm the live Alembic head chain.

## Tests map
- Backend tests: `backend/tests`, `integration_tests`, plus focused regression coverage for compatibility bridges.
- Frontend tests: `frontend/src/__tests__` covering routing, permissions, API clients, tasks, dashboards, operations pages, and client portal slices.
- This wave added verification for named compatibility bridges and PWA-capable frontend build output.

## Static / placeholder frontend pages map
Confirmed as already backed by real data/projection flows rather than pure static cards:
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

Still not complete relative to the super-TZ:
- full attention center UX,
- full data quality center UX,
- full offline queue/conflict-resolution UX,
- richer role-based dashboard projections and external portal operational slices.

## Stub / mock / deferred backend map
Factually confirmed problems:
- `backend/app/api/routes/ws_stub.py` -> WebSocket 501 stub still remains.
- `backend/app/celery/tasks/document_jobs_required.py` -> document step wrappers are real tenant-aware bridges for render/build/sign/EDO/index; `export_report_job` and `sync_integration_job` now support real internal bridge handlers when wired, but still preserve deferred compatibility envelopes by default.
- `backend/app/services/pipelines_orchestrator.py` -> still a fat orchestrator with partial internal decomposition.
- `backend/app/services/integrations/stubs.py` -> 1C/ЭДО/ФРДО/ЕИСОТ stubs remain clearly non-production.
- `backend/app/api/routes/approval_signing_v1.py`, `approval_orchestration.py`, `edo_workflow.py` -> still rely on stub/mock provider defaults and need production adapter hardening later; responses now expose additive provider metadata so non-production adapters are no longer silently indistinguishable from certified ones.
- `frontend/vite.config.ts` had no real PWA plugin setup before this wave; this wave adds a real plugin/manifest/service-worker baseline, but not the full offline queue/conflict stack requested in the super-TZ.
- Several pages are still foundational/aggregated rather than domain-complete operational consoles.

## Fat files requiring decomposition
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
- `backend/app/tasks.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `backend/app/api/routes/edo_workflow.py`

## Legacy / compatibility pairs and risky paths
- `backend/app/api/v1/router.py` vs `backend/app/api/v1/route_groups.py`.
- `backend/app/models/models.py` vs focused model modules.
- `backend/app/tasks.py` vs `backend/app/celery/tasks/document_jobs_required.py`.
- Approval/sign/EDO spread across `approval_signing_v1.py`, `approval_orchestration.py`, `edo_workflow.py`.
- Vite SPA shell vs new generated PWA shell/service worker.

## Gaps relative to the super-TZ
### P0 partially addressed
- Repo audit documented.
- `router.py` decomposition is only partially established via route groups, not finished.
- `models.py` decomposition is still partial.
- Compatibility background jobs are hardened, but not all document/report/integration chains are fully centralized.
- PWA setup moved from absent to real baseline, but offline queue/sync/conflict UX remains open.

### P0/P1 still open
- Full tenant/authz/audit/correlation-id sweep across all business endpoints.
- Centralized document readiness score and blocker explanations.
- Universal tasks/timeline/attention layer.
- Data quality issue model and dashboards.
- Production-grade workflow/sign/EDO adapters.

## What changed in this wave
- Added a real Vite PWA baseline with manifest, service worker generation, runtime registration, and asset/runtime caching strategy.
- Hardened `document_jobs_required.py` so compatibility task names can execute named internal bridges for report export and integration sync instead of being permanently hardcoded stubs.
- Added additive provider metadata to approval/sign/EDO responses so stub/mock/disabled providers are explicitly marked as non-production.
- Added regression tests for the bridge behavior and provider classification seam.
- Refreshed wave docs to clearly separate implemented hardening from remaining gaps.
