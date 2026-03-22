# CODEX Wave Plan

_Date:_ 2026-03-22

## Strategy for this wave
1. Audit the repo first and document actual roots, route maps, placeholder surfaces, stubs, and risky compatibility seams.
2. Make one bounded hardening slice that improves platform reliability without a rewrite.
3. Preserve API/task compatibility while clarifying canonical composition and bridge behavior.
4. Add focused tests and refresh wave docs.

## Executed this wave
- Refreshed the wave audit with factual backend/frontend maps, confirmed stubs, and super-TZ gap tracking.
- Extracted approval/EDO/sign models into `backend/app/models/approval_workflow.py` while keeping compatibility imports in `backend/app/models/models.py`.
- Split pipeline step handlers into `backend/app/services/pipeline_step_handlers.py` and kept `PipelineOrchestrator` as the orchestrating compatibility surface.
- Hardened `backend/app/celery/tasks/document_jobs_required.py` so legacy document-job task names now execute real tenant-aware orchestrator steps for covered flows instead of returning stub-only envelopes.
- Added backend regression tests for the refactored dispatch and document-job compatibility bridge behavior.

## Why this slice was chosen
- It is backward-compatible.
- It removes a confirmed stubbed execution seam without changing public task names.
- It creates safer foundations for future decomposition of `router.py`, `models.py`, workflow/EDO/sign task convergence, and audit tooling.

## Intentionally deferred
- Large-scale decomposition of the remaining `backend/app/models/models.py` sections.
- PWA plugin/service worker/offline queue implementation.
- Replacing mock/stub providers with certified production adapters.
- Broad frontend rewiring, because the listed placeholder pages are already on real data flows and did not require a fresh rewrite in this wave.

## Recommended next moves
1. Continue extracting the remaining approval workflow/process/task models from `backend/app/models/models.py` into focused modules.
2. Keep shrinking `backend/app/services/pipelines_orchestrator.py` around execution state/audit/retry helpers now that step handlers are extracted.
3. Normalize approval/sign/EDO routes onto clearer canonical paths with shared provider policy guards.
4. Use the new route-group metadata to generate route-audit docs/tests automatically.
