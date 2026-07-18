# CODEX Wave Next Steps

_Date:_ 2026-03-22

1. Continue extracting approval process/task/status/user-webhook models from `backend/app/models/models.py` now that approval/EDO/sign primitives live in `backend/app/models/workflow.py` and the legacy v1 route has an `approval_signing.py` compatibility layer.
2. Keep shrinking `backend/app/services/pipelines_orchestrator.py` by extracting audit/retry/state helpers after the new `pipeline_step_handlers.py` split.
3. Normalize approval/sign/EDO route families onto clearer canonical paths while preserving existing compatibility routes.
4. Expand the runtime bridge pattern to the remaining compatibility-only jobs only when a real orchestrator path exists.
5. Begin a dedicated tenant/authz/audit/correlation-id sweep for high-risk business endpoints.
6. Replace non-production provider adapters with certified integrations behind the explicit provider registry seam.
7. Build the next PWA wave on top of the installed baseline: tenant-aware offline queue, sync status UI, retry/resume flows, and conflict resolution instead of overstating current readiness.
