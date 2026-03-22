# CODEX Wave Audit

_Date:_ 2026-03-22

## Scope of this audit wave
- This wave did a factual repo audit first and then applied a compatibility-safe backend hardening slice around document/pipeline orchestration.
- No massive rewrite was attempted; the current wave focuses on reducing explicit stub behavior while preserving existing contracts.

## Canonical backend/frontend roots
- Backend bootstrap and API composition roots: `backend/app/main.py`, `backend/app/api/app.py`, `backend/app/api/v1/router.py`, `backend/app/api/v1/route_groups.py`.
- Backend domain/service roots: `backend/app/api/routes`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/celery/tasks`.
- Frontend runtime roots: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/router/AppRouter.tsx`, `frontend/src/router/routeGroups.tsx`, `frontend/src/pages`, `frontend/src/api`, `frontend/src/stores`.

## Active entrypoints
- ASGI app: `backend/app/main.py` -> `backend/app/api/app.py`.
- API v1 composition: `backend/app/api/v1/router.py` plus grouped registration in `backend/app/api/v1/route_groups.py`.
- Celery worker/task roots: `backend/app/worker.py`, `backend/app/tasks.py`, `backend/app/celery/tasks/*`.
- Frontend app: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `frontend/src/router/AppRouter.tsx`.

## Backend route map
- Auth / tenancy / admin: auth, tenancy context, admin users, audit, billing, webhooks, API tokens.
- Operational registries: companies, sites, persons, contractors, inspections, prescriptions, incidents, tasks, training, PPE, medical.
- Document core: templates, branding, headers, replace, pdf, pipelines, jobs, packs, workflow, approvals/sign/EDO.
- PWA/offline-facing routes exist, but the full offline contract/service-worker stack is still incomplete.

## Frontend route/page map
- Permission-aware grouped routes are composed in `frontend/src/router/routeGroups.tsx`.
- Current enterprise surface includes dashboards, documents/templates/generation, packs/jobs/archive/search, approvals/EDO, inspections, incidents, training, PPE/warehouse, CRM-finance, admin, client portal, and the static-to-real operational pages already converted in prior waves.

## Active module map
- Canonical API grouping is already moving into `backend/app/api/v1/route_groups.py`; `backend/app/api/v1/router.py` is still a compatibility-heavy composition root and remains a decomposition candidate.
- ORM decomposition has started around `backend/app/models/document.py`, `document_core.py`, `tenanting.py`, `safety_core.py`, `safety_ops.py`, `risk.py`, while `backend/app/models/models.py` still acts as a compatibility mega-module.
- Pipeline/document orchestration spans `backend/app/services/pipelines_orchestrator.py`, `backend/app/celery/tasks/document_jobs_required.py`, `backend/app/celery/tasks/job_steps.py`, and `backend/app/tasks.py`.
- Frontend build/runtime stays centered around Vite + React; `frontend/vite.config.ts` still lacks full production-grade PWA plugin wiring.

## Migration heads
- No new migration was added in this wave.
- The repo still relies on existing migration heads under `backend/app/migrations/versions`.
- Because this wave stayed compatibility-safe, DB schema shape was intentionally left unchanged.

## Tests map
- Backend core/tenancy/authz coverage remains under `tests/` with dedicated suites for tenant guards, audit, auth, billing, client portal, job engine, and pipeline orchestration.
- This wave specifically extended `tests/test_next39_pipeline_orchestrator.py` to cover internal non-stub pipeline step handlers and deferred job wrapper semantics.
- Frontend tests already exist for route/screen regressions, but this wave did not change frontend runtime behavior.

## Static / placeholder frontend pages map
Previously documented as converted to real data in earlier waves:
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

Still requiring deeper validation or additional projection hardening against the super-TZ:
- dashboards / attention projections,
- full client-portal readiness/status/history flows,
- PWA/offline queue/conflict UX,
- data quality center UX.

## Stub / mock / deferred backend map
Factually confirmed during this audit:
- `backend/app/api/routes/ws_stub.py` -> WebSocket 501 stub remains deferred.
- `backend/app/celery/tasks/document_jobs_required.py` -> legacy bridge tasks existed as stub-like placeholders; this wave reduced explicit `stub` statuses but the bridge remains deferred for full provider-backed execution.
- `backend/app/services/pipelines_orchestrator.py` -> partial stub step handlers existed; this wave replaced the most explicit ones (`sign`, `verify_signature`, `send_edo`, `index_file_content`) with internal orchestration/projection handlers, but the file is still bloated and needs more decomposition.
- `backend/app/services/integrations/stubs.py` -> 1C/ЭДО/ФРДО/ЕИСОТ non-production stubs remain and are still clearly non-certified.
- `backend/app/api/routes/approval_signing_v1.py`, `approval_orchestration.py`, `edo_workflow.py` -> mock/stub provider paths remain in active use and still need production adapter hardening.
- `frontend/vite.config.ts` -> still no real PWA plugin/service-worker setup.

## Fat files requiring decomposition
- `backend/app/api/v1/router.py` — still large and compatibility-sensitive.
- `backend/app/models/models.py` — still the largest persistence risk surface.
- `backend/app/services/pipelines_orchestrator.py` — still too broad, even after this wave’s handler hardening.
- `backend/app/api/routes/approval_signing_v1.py` and `backend/app/api/routes/edo_workflow.py` — multiple responsibilities mixed together.

## Legacy / compatibility pairs and risky paths
- `backend/app/api/v1/router.py` <-> `backend/app/api/v1/route_groups.py`.
- `backend/app/models/models.py` <-> extracted compatibility modules like `backend/app/models/tenanting.py`.
- `backend/app/tasks.py` <-> `backend/app/celery/tasks/*` task namespaces.
- Approval/sign/EDO route families currently overlap between `approval_signing_v1.py`, `approval_orchestration.py`, and `edo_workflow.py`.

## Factually confirmed gaps vs super-TZ
- Full tenant/authz/audit consistency pass is not finished repo-wide; this wave only hardened a bounded document pipeline slice.
- Document core centralization is still partial: the chain exists, but dependency graph, readiness blockers/actions, reproducibility snapshots, and version diff foundations are not uniformly complete.
- Universal tasks/timeline/attention center is not yet a complete cross-domain operational layer.
- Persistent data quality layer is still a gap.
- Real PWA setup, offline shell, queue, sync UI, conflict resolution, and media lifecycle remain gaps.
- Production-grade approval/sign/EDO providers are still not implemented; current abstractions are present but rely on mock/stub providers.

## This wave’s actual hardening delta
- Replaced explicit pipeline stub handlers for `sign`, `verify_signature`, `send_edo`, and `index_file_content` with internal deterministic handlers or provider-backed calls through the existing integration abstraction.
- Reduced legacy Celery bridge task responses in `document_jobs_required.py` from opaque `stub` returns to explicit accepted/deferred bridge envelopes.
- Added regression tests covering the new orchestrator handlers and wrapper semantics.
