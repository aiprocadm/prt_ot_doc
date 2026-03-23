# Corporate Readiness Audit

Date: 2026-03-23

## Scope and method
- Re-audited runtime code with one question: can this be operated as a real corporate platform (reliable, consistent, tenant-safe, permission-safe, operationally usable).
- Used factual checks in backend/frontend code and existing docs.
- Did not assume super-spec completion; compared target state to current implementation.

## Factual repository snapshot
- Backend route files: 55 in backend/app/api/routes.
- Frontend page files: 75 in frontend/src/pages.
- Migrations: 71 in backend/app/migrations/versions.
- Largest backend hotspots by size:
  - backend/app/models/models.py: 122658 bytes (~120 KB)
  - backend/app/tasks.py: 76227 bytes (~74 KB)
  - backend/app/api/v1/router.py: 55032 bytes (~54 KB)
  - backend/app/api/routes/risk.py: 48467 bytes (~47 KB)
  - backend/app/services/pipeline.py: 43285 bytes (~42 KB)
  - backend/app/api/routes/packs.py: 37916 bytes (~37 KB)
  - backend/app/api/routes/documents.py: 33529 bytes (~32 KB)
  - backend/app/services/pipelines_orchestrator.py: 31370 bytes (~30 KB)

## Executive summary
The codebase is already a strong enterprise foundation, especially in document core and tenancy/authz. The key gap is not breadth of modules, but depth hardening: cross-module consistency, operational workspace UX, removal/isolation of corporate-blocking stub and deferred seams, stronger data quality/readiness layer, and practical mobile/offline execution model.

## Confirmed strong foundations
- Document core is deep and production-oriented (templates, versioning, preview, branding, replace, PDF, packs, pipelines).
- Tenancy/authz and audit foundations are materially above average for this scope.
- Backend is modular; not only a flat route bundle.
- Client portal, billing, notifications, risk/training/PPE/incidents/inspections foundations are present.
- Operational and acceptance docs are extensive.

## Mandatory confirmed facts from code
The following facts are confirmed and treated as enterprise-readiness constraints:

- backend/app/api/routes/ws_stub.py: WebSocket path is deferred/stub.
- backend/app/celery/tasks/document_jobs_required.py: deferred/stub compatibility behavior is present.
- backend/app/services/pipeline_step_handlers.py: deferred stages are present.
- backend/app/services/integrations/stubs.py: stub providers for 1C/EDO/FRDO/EISOT are present.
- backend/app/api/routes/approval_signing_v1.py: default provider uses stub semantics.
- backend/app/api/routes/approval_orchestration.py: mock provider semantics are present.
- backend/app/api/routes/edo_workflow.py: mock/stub semantics are present.
- frontend/vite.config.ts: PWA plugin and runtime caching are already present.
- /api/pwa/bootstrap: now has stronger authenticated projection in current branch; still requires further hardening for field/offline usability (queue/conflicts/drafts UX and scenario coverage).

## Foundation-level / partial areas
- Several frontend surfaces remain thin wrappers, navigation shells, or partial operational screens.
- Operational UX is not yet unified as role workspace + attention center + readiness blockers.
- Cross-module consistency of tenant/authz/errors/audit/correlation is not yet fully normalized endpoint-by-endpoint.

## Priority frontend screens for operational hardening
- frontend/src/pages/contractors/ContractorsPage.tsx
- frontend/src/pages/reference/ReferencePage.tsx
- frontend/src/pages/settings/SettingsPage.tsx
- frontend/src/pages/activities/ActivitiesPage.tsx
- frontend/src/pages/medical/MedicalPage.tsx
- frontend/src/pages/fire-safety/FireSafetyPage.tsx
- frontend/src/pages/fire-training/FireTrainingPage.tsx
- frontend/src/pages/fire-inspections/FireInspectionsPage.tsx
- frontend/src/pages/inspection-checklists/InspectionChecklistsPage.tsx
- frontend/src/pages/inspection-plans/InspectionPlansPage.tsx
- frontend/src/pages/inspection-prep/InspectionPrepPackagesPage.tsx
- Selected dashboard and client-portal pages currently acting as projection wrappers.

## Architecture debt and duplication
- Fat files listed above are now in the high-risk maintenance zone and should be split incrementally.
- Parallel module layering exists and should be canonized:
  - backend/app/modules/approval
  - backend/app/modules/approvals

## Corporate-blocking gaps by impact
Tier 1:
1. Cross-platform consistency (tenant/authz/errors/audit/correlation).
2. Operational workspace layer (attention center, inbox, blockers, recommendations, deep links).
3. Stub/mock/deferred isolation and non-production mode transparency.
4. Persisted data quality + readiness blockers.
5. Practical mobile/offline model (queue, retry/resume, conflicts, drafts, selected field scenarios).
6. Admin governance and diagnostics usable for rollout.

Tier 2:
1. Reliability normalization (retries, DLQ/poison, watchdog, integrity checks).
2. Further document core centralization and deterministic lifecycle visibility.
3. UX declutter and progressive disclosure across overloaded screens.

## Audit conclusion
The platform is suitable as a corporate product base, but not yet enterprise-complete for broad production rollout. The correct next step is depth hardening in phases, not functional expansion in breadth and not a rewrite.
