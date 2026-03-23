# Corporate Readiness Audit

Date: 2026-03-23

## Scope and method
- Audit objective: verify if runtime code is ready for enterprise exploitation (reliability, consistency, tenant safety, permission safety, operational usability).
- Method: factual code checks in backend/frontend plus current readiness docs.
- Constraint: no assumptions from target super-spec without runtime verification.

## Factual repository snapshot
- Backend route files: 56 in backend/app/api/routes.
- Frontend page files: 74 in frontend/src/pages.
- Migrations: 71 in backend/app/migrations/versions.
- Largest backend hotspots:
  - backend/app/models/models.py: 122658 bytes (~120 KB)
  - backend/app/tasks.py: 76227 bytes (~74 KB)
  - backend/app/api/v1/router.py: 55032 bytes (~54 KB)
  - backend/app/api/routes/risk.py: 48800 bytes (~47 KB)
  - backend/app/services/pipeline.py: 43285 bytes (~42 KB)
  - backend/app/api/routes/packs.py: 39059 bytes (~37 KB)
  - backend/app/api/routes/documents.py: 33441 bytes (~32 KB)
  - backend/app/services/pipelines_orchestrator.py: 31370 bytes (~30 KB)

## Executive summary
The codebase is already a strong enterprise foundation, especially in document core and tenancy/authz/audit. Main gaps are depth and consistency: unified operational workspace, consistent policy contracts across modules, transparent handling of non-production providers, practical offline/field UX, and reliability normalization.

## Confirmed strengths
- Deep document core: templates, versioning, preview, branding, replace, PDF, packs, pipeline orchestration.
- Tenant/authz base is solid and mostly above average for similar enterprise platforms.
- Backend is module-oriented, not just a flat route set.
- Foundations exist for client portal, billing, notifications, risk, training, PPE, incidents, inspections.
- Strong operational documentation baseline and acceptance artifacts.

## Mandatory confirmed facts (runtime code)
- backend/app/api/routes/ws_stub.py: WebSocket path is deferred/stub.
- backend/app/celery/tasks/document_jobs_required.py: deferred/stub compatibility behavior exists.
- backend/app/services/pipeline_step_handlers.py: deferred stages exist.
- backend/app/services/integrations/stubs.py: stub providers exist for 1C/EDO/FRDO/EISOT.
- backend/app/api/routes/approval_signing_v1.py: default provider uses stub semantics.
- backend/app/api/routes/approval_orchestration.py: mock provider semantics exist.
- backend/app/api/routes/edo_workflow.py: mock/stub semantics exist.
- frontend/vite.config.ts already includes vite-plugin-pwa and runtime caching.
- Historical archive baseline: /api/pwa/bootstrap had simplified payload semantics (including missing user projection depth) and required hardening.
- Current branch status: /api/pwa/bootstrap is already richer than minimal stub payload (real user/roles/permissions, route permissions, dictionaries, offline/sync projections), but still needs enterprise field hardening on conflict resolution UX, queue transparency and scenario depth.

## Production-usable vs foundation-level
Production-usable core:
- Document lifecycle foundation and many business registries with tenant-aware data.
- Key auth/tenant controls and audit infrastructure.

Foundation-level or partial:
- Role-based operational cockpit is not fully unified yet.
- Readiness blockers and recommended actions are not consistently surfaced in all workflows.
- Offline model exists technically, but field ergonomics and conflict handling remain partial.

## Priority frontend areas (operational hardening)
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
- Selected dashboard and client-portal projection views.

## Architecture debt and duplication
- Fat files listed above are in a high maintenance cost zone and should be split incrementally without breaking behavior.
- Parallel module structures confirmed:
  - backend/app/modules/approval
  - backend/app/modules/approvals

## Corporate rollout blockers by impact
Tier 1 blockers:
1. Endpoint-level consistency normalization for tenant/authz/errors/audit/correlation.
2. Unified operational workspace layer (attention center, inbox, blockers, recommendations, deep links).
3. Clear isolation and diagnostics for stub/mock/deferred providers.
4. Persisted data quality layer with blocker severity and scenario impact.
5. Practical mobile/offline field contour (queue, retry/resume, conflicts, drafts).
6. Operational admin diagnostics for rollout readiness.

Implemented in this wave (first practical consistency step):
- PWA sync endpoints enforce authenticated owner semantics and server-controlled sensitive fields:
  - /api/pwa/sync/batch now ignores client-supplied tenant/user/status.
  - /api/pwa/media/commit now ignores client-supplied tenant/user/upload_status.
  - /api/pwa/sync/status/{batch_id} now applies owner-or-admin access checks.

Tier 2 blockers:
1. Retry/DLQ/watchdog/integrity normalization.
2. Deeper deterministic lifecycle explainability in document core.
3. UX declutter and progressive disclosure across overloaded modules.

## Audit conclusion
This repository is enterprise-capable as a base product but not yet enterprise-complete for broad rollout. Correct strategy is depth hardening in waves, without rewrite and without sacrificing existing working features.
