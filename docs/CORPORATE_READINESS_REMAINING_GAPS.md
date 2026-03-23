# Corporate Readiness Remaining Gaps

_Date:_ 2026-03-23

## Confirmed critical stub/mock/deferred gaps
- `backend/app/api/routes/ws_stub.py` remains explicitly deferred.
- `backend/app/celery/tasks/document_jobs_required.py` still emits deferred compatibility envelopes when runtime bridges are missing.
- `backend/app/services/pipeline_step_handlers.py` still returns deferred stage results when integrations are disabled.
- `backend/app/services/integrations/stubs.py` still provides explicit non-production adapters for 1C, EDO, FRDO, and EISOT.
- `backend/app/api/routes/approval_signing_v1.py` still carries `stub` defaults in important request models.
- `backend/app/api/routes/approval_orchestration.py` still contains mock-provider behavior.
- `backend/app/api/routes/edo_workflow.py` still contains mock/stub semantics, including `mock` provider defaults.

## Platform consistency gaps
- No endpoint-by-endpoint verification is complete yet for every business route family covering tenant context, authz, structured errors, correlation-id propagation, and sensitive-action audit.
- Recent waves expanded audit coverage significantly, but full normalization across all legacy/alias routes and bulk/export/search edges still remains.
- Background job behavior has not yet been normalized platform-wide for retries, DLQ/poison handling, watchdogs, and failed-job diagnostics.
- Permission behavior is still uneven across some read/write/bulk/export/search surfaces.

## Operational workspace gaps
- No single role-based workspace layer exists yet.
- No unified attention center exists yet.
- No cross-module task inbox exists yet.
- No shared readiness-blocker presentation with reasons and recommended actions exists yet.
- Recent drafts, recent items, and recommendation blocks are still partial/distributed.
- Entity-card consistency remains incomplete.

## Document-core gaps
- Full lifecycle visibility from template through archive is not yet unified into one readiness-driven operational surface.
- Template resolution by system / tenant / company / site scope still needs hardening.
- Readiness score, reasons, and recommended actions are not yet consistently exposed.
- Dependency mapping and deterministic render-snapshot visibility remain incomplete.
- Idempotent rerun and progress/reporting contracts still need hardening.

## Data-quality and blocker gaps
- No full persisted issue layer yet for employees, companies/sites, templates/documents, training, PPE, and contractors.
- No blocker severity + scenario-impact model is integrated end-to-end into dashboards, attention center, and entity readiness.

## Mobile/PWA gaps
- PWA installability and runtime caching are in place, and `/api/pwa/bootstrap` already returns authenticated projections (user, permissions, dictionaries, sync/conflict diagnostics).
- Frontend offline queue UX remains incomplete.
- Sync-state UX is still incomplete.
- Conflict-resolution UX is still missing.
- Draft persistence and retry/resume semantics are still partial.
- Selected field scenarios are not yet complete, especially media/photo sync and practical mobile workflows.

## Admin / governance / diagnostics gaps
- Admin is still not a fully operational corporate governance console.
- Tenant readiness, provider mode, queues/jobs, data quality, billing/usage, and environment diagnostics need stronger consolidation.

## Reliability / runbook gaps
- Retries consistency, poison handling, watchdogs, cleanup jobs, and integrity checks need a dedicated hardening pass.
- `docs/SETUP.md`, `docs/TESTING.md`, `docs/OBSERVABILITY.md`, and `docs/RUNBOOK.md` still need to be updated as part of the dedicated reliability wave.

## Structural debt to address incrementally
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
- `backend/app/tasks.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `backend/app/api/routes/edo_workflow.py`
