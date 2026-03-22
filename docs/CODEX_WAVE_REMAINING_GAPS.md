# CODEX Wave Remaining Gaps

_Date:_ 2026-03-22

## P0/P1 gaps still open
- Repo-wide tenant-context rejection, authz coverage, object-level restrictions, and structured error consistency are still not fully closed.
- Document readiness score, explainable blockers/actions, dependency graph, diff/compare foundations, and reproducible render snapshots are still partial.
- Universal task/timeline/attention-center layer is not fully unified across incidents, inspections, prescriptions, training, readiness blockers, and data-quality blockers.
- Persistent data quality model/service/projection is still missing as a complete layer.
- Real PWA setup, offline queue, sync/conflict UX, and media lifecycle remain missing.
- Production-grade approval/sign/EDO adapters are still absent.

## Known deferred/stub areas
- `backend/app/api/routes/ws_stub.py`
- `backend/app/services/integrations/stubs.py`
- `backend/app/api/routes/approval_signing_v1.py`
- `backend/app/api/routes/approval_orchestration.py`
- `backend/app/api/routes/edo_workflow.py`
- `frontend/vite.config.ts`

## Structural risks
- `backend/app/api/v1/router.py`
- `backend/app/models/models.py`
- `backend/app/services/pipelines_orchestrator.py`
