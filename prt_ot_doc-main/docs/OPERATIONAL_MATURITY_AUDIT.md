# Operational Maturity Audit (main, 2026-03-24)

## Scope and method

This audit is fact-based for the current main branch revision and focuses on operational maturity (daily usability, consistency, reliability), not only feature presence.

Data sources:
- backend and frontend route/page inventory
- key heavy modules and architecture risk points
- confirmed stub/mock/deferred surfaces
- current role workspace/attention/task/readiness capabilities
- admin/diagnostics and PWA/offline coverage

## Fact baseline for this revision

Measured from repository tree:
- backend route files: 56
- frontend page files: 75
- migration files: 74
- test/artifact files in test contours: 520

Heavy files (bytes):
- backend/app/models/models.py: 122658
- backend/app/tasks.py: 76227
- backend/app/api/v1/router.py: 55032
- backend/app/api/routes/risk.py: 48800
- backend/app/services/pipeline.py: 43285
- backend/app/api/routes/packs.py: 39059
- backend/app/api/routes/documents.py: 33441
- backend/app/api/routes/approval_signing_v1.py: 31513
- backend/app/services/pipelines_orchestrator.py: 31370

## Confirmed facts required by target spec

Confirmed by code:
- backend/app/api/routes/ws_stub.py = deferred websocket (501)
- backend/app/celery/tasks/document_jobs_required.py = compatibility/deferred semantics for bridges
- backend/app/services/pipeline_step_handlers.py = deferred stage result when integration disabled
- backend/app/services/integrations/stubs.py = stub providers (1c, edo, frdo, eisot)
- backend/app/api/routes/approval_signing_v1.py = default provider stub
- backend/app/api/routes/approval_orchestration.py = default provider mock
- backend/app/api/routes/edo_workflow.py = default provider mock/stub webhook path
- frontend/vite.config.ts already includes vite-plugin-pwa with manifest and runtimeCaching
- /api/pwa/bootstrap (backend/app/api/routes/pwa_sync.py) already returns current_user, route_permissions, dictionaries, offline_queue, sync_state, diagnostics

## Operational maturity status by domain

### Already usable in daily operations (foundation+)
- Document core baseline: template/version/preview/branding/replace/pdf/packs flows exist and are integrated.
- Tenant/authz foundation exists across major backend paths.
- Multiple pages already use real snapshots/projections (admin, contractors, reference, medical, fire safety, inspection prep workspace).
- Workspace attention and task inbox APIs exist (backend/app/api/routes/workspace.py) with blockers and recommendations.
- Integration readiness endpoint exists with provider_mode and production-ready metadata.

### Projection/foundation screens (usable but not yet high-maturity UX)
- Several operational pages show real data but remain projection wrappers with limited guided workflows.
- Next actions/deep links/bulk actions/empty-state coaching are uneven by module.
- Cross-page action semantics and blockers visibility are inconsistent.

### Stub/mock/deferred corporate blockers
- Approval/sign and EDO workflows still expose non-production providers by default.
- Deferred compatibility bridge semantics remain in critical async/job surfaces.
- WebSocket realtime remains deferred to REST fallback.

### Consistency gaps (backend/frontend)
- Permission, correlation-id and error contracts are strong in some routes and weaker in others.
- Sensitive action audit exists but is not uniformly exposed in role-oriented operational cockpit.
- Background orchestration has tenant/correlation handling in key paths, but consistency should be normalized end-to-end for all critical workflows.

### Architecture debt and fat-file risk
- High concentration of behavior in large files increases regression risk and slows safe iteration.
- Mixed boundary style: mature moduleized surfaces coexist with monolithic route/service files.

## Role-based workspaces and operational UX assessment

What already helps:
- workspace attention summary, blockers, recommendations
- workspace task inbox
- readiness signals in dashboard-like endpoints

What still limits enterprise usability:
- role cockpit is not yet a unified default post-login experience across modules
- incomplete cross-domain task projection (documents/training/prescriptions/incidents/ppe/contractors/NPA)
- limited scenario-first UX (next best action, deep links, contextual blockers resolution)

## PWA/field mode maturity assessment

Strengths:
- PWA infra is already present and active (manifest + runtime caching).
- bootstrap includes user, permissions, dictionaries, queue state and diagnostics.
- offline queue/conflict metadata already present in payload.

Gaps to close:
- broader offline bootstrap dictionaries for field workflows
- stronger retry/resume and conflict-resolution UX loops in UI
- clearer end-user sync diagnostics and guided recovery
- stronger draft durability and conflict replay consistency in critical scenarios

## Conclusion

Current revision is a strong enterprise foundation, but not yet a fully hardened corporate daily-use platform. The key gap is operational maturity depth (consistency, guided workflows, blockers/readiness explainability, provider mode transparency), not breadth of modules.
