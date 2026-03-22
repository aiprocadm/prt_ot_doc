# CODEX Wave Plan

_Date:_ 2026-03-21

## Executed in this pass
1. Refresh repo audit with canonical roots, route maps, placeholder map, and explicitly confirmed stub/deferred areas.
2. Add one compatibility-safe backend operational endpoint for medical exams instead of keeping the medical screen as showcase-only.
3. Convert priority placeholder frontend pages to real tenant-aware API flows without changing route contracts.
4. Cover the new real-data pages with focused frontend regression tests.

## Delivered
- `GET /medical/exams` added as a tenant-aware read registry for real medical data.
- Real-data conversions completed for contractors, reference, settings, activities, medical, fire-safety, fire-training, fire-inspections, inspection-checklists, inspection-plans, inspection-prep packages, and admin.
- `frontend/src/api/operations.ts` introduced as a thin aggregation layer over existing backend contracts.
- Docs refreshed for audit/plan/static-to-real mapping.

## Explicitly deferred to next wave
- `ws_stub.py`, `document_jobs_required.py`, `pipelines_orchestrator.py`, integration stubs, approval/sign/EDO production adapters.
- Real PWA plugin + manifest/service worker/offline queue + conflict UI.
- Persistent data quality center and attention center.
- Deeper compatibility split of `backend/app/models/models.py` and further router decomposition.

## Next safe moves
1. Replace document/pipeline stubs with real internal orchestration where contracts already exist.
2. Extract another bounded compatibility layer out of `backend/app/models/models.py`.
3. Implement production-grade PWA wiring in `frontend/vite.config.ts` and field sync UX.
4. Add dedicated backend projections for attention center and data quality center instead of frontend-only aggregation.
