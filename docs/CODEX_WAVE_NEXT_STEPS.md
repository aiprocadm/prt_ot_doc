# CODEX Wave Next Steps

_Date:_ 2026-03-22

1. Extract pipeline step handlers from `backend/app/services/pipelines_orchestrator.py` into focused modules with compatibility imports.
2. Start decomposing `backend/app/models/models.py` by carving out an approvals/EDO/sign compatibility module.
3. Normalize approval/sign/EDO route families onto clearer canonical paths while preserving existing compatibility routes.
4. Use `describe_router_groups()` to automate route-audit docs/tests and detect risky path drift.
5. Begin a dedicated tenant/authz/audit/correlation-id sweep for high-risk business endpoints.
6. Plan the real PWA plugin/service-worker/offline queue wave separately instead of overstating readiness.
