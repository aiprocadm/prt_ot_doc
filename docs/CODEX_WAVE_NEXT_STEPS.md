# CODEX Wave Next Steps

_Date:_ 2026-03-22

1. Continue extracting approval process/task/status models from `backend/app/models/models.py` now that approval/EDO/sign primitives live in `backend/app/models/approval_workflow.py`.
2. Keep shrinking `backend/app/services/pipelines_orchestrator.py` by extracting audit/retry/state helpers after the new `pipeline_step_handlers.py` split.
3. Normalize approval/sign/EDO route families onto clearer canonical paths while preserving existing compatibility routes.
4. Expand the runtime bridge pattern to the remaining compatibility-only jobs only when a real orchestrator path exists.
5. Begin a dedicated tenant/authz/audit/correlation-id sweep for high-risk business endpoints.
6. Plan the real PWA plugin/service-worker/offline queue wave separately instead of overstating readiness.
