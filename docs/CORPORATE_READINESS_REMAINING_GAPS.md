# Corporate Readiness Remaining Gaps

_Date:_ 2026-03-22

## Confirmed critical gaps
- `backend/app/api/routes/ws_stub.py` remains deferred.
- `backend/app/celery/tasks/document_jobs_required.py` still preserves deferred compatibility behavior for selected jobs when no runtime bridge is configured.
- `backend/app/services/pipeline_step_handlers.py` is only a partial extraction and does not yet eliminate all deferred pipeline-stage behavior in the wider orchestration contour.
- `backend/app/services/integrations/stubs.py` still provides explicit non-production adapters for 1C / EDO / FRDO / EISOT.
- `backend/app/api/routes/approval_signing_v1.py` still defaults to non-production provider behavior in important paths.
- `backend/app/api/routes/approval_orchestration.py` still contains mock-provider semantics.
- `backend/app/api/routes/edo_workflow.py` still contains mock/stub semantics.

## Platform-wide gaps
- No full endpoint-by-endpoint tenant/authz/audit/correlation review has been completed yet.
- No unified attention center / work inbox / readiness blocker UX exists across modules.
- No persisted enterprise-wide data quality issue layer exists yet.
- Admin diagnostics are useful but not yet a full corporate governance console.
- Runbooks and observability docs still need a dedicated operational maturity pass.

## PWA/mobile-specific gaps
- Frontend offline queue model is still incomplete.
- Sync state UI, retry/resume UI, and conflict resolution UI are still missing.
- Draft persistence and selected field workflows remain partial.
- Media/photo sync is not yet represented as a complete user-facing operational flow.

## Structural debt
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
- `backend/app/tasks.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `backend/app/api/routes/edo_workflow.py`
