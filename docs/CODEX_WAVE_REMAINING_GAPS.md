# CODEX Wave Remaining Gaps

_Date:_ 2026-03-22

## Still-open P0/P1 gaps
- Full tenant/authz/audit/correlation-id consistency sweep across all business endpoints.
- Centralized document readiness scoring and blocker/action explanations.
- Universal tasks/timeline/attention center operational layer.
- Data quality persistent issue model and dashboards.
- Production-grade workflow/sign/EDO provider adapters.
- Tenant-aware offline queue, sync-status, media lifecycle, resume/retry, and conflict-resolution UX on top of the new PWA baseline.

## Confirmed deferred/stubbed areas
- `backend/app/api/routes/ws_stub.py`
- `backend/app/services/integrations/stubs.py`
- Mock/stub provider paths inside approval/sign/EDO routes
- Compatibility wrapper task names remain for backward compatibility; `export_report_job` / `sync_integration_job` now have a real runtime bridge seam, but remain envelope-only unless internal handlers are actually wired
- Mock/stub providers are now explicitly marked as non-production metadata, but certified adapters are still absent.

## Structural debt
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
- `backend/app/tasks.py`
