# CODEX Wave Plan

_Date:_ 2026-03-22

## Strategy for this wave
1. Audit the repo first and document actual roots, route maps, placeholder surfaces, stubs, and risky compatibility seams.
2. Make one bounded hardening slice that improves platform reliability without a rewrite.
3. Preserve API/task compatibility while clarifying canonical composition and bridge behavior.
4. Add focused tests and refresh wave docs.

## Executed this wave
- Refreshed the wave audit with factual backend/frontend maps, confirmed stubs, and super-TZ gap tracking.
- Strengthened API composition metadata in `backend/app/api/v1/route_groups.py` by promoting route groups into explicit registries plus a machine-readable `describe_router_groups()` helper.
- Hardened `backend/app/celery/tasks/document_jobs_required.py` so legacy document-job task names now return explicit compatibility-wrapper envelopes with orchestrator and deferred-bridge metadata.
- Added backend regression tests for route-group descriptions and document-job compatibility wrappers.

## Why this slice was chosen
- It is backward-compatible.
- It reduces ambiguity around active route composition and document-job bridge behavior.
- It creates safer foundations for future decomposition of `router.py`, workflow/EDO/sign task convergence, and audit tooling.

## Intentionally deferred
- Large-scale decomposition of `backend/app/models/models.py`.
- PWA plugin/service worker/offline queue implementation.
- Replacing mock/stub providers with certified production adapters.
- Broad frontend rewiring, because the listed placeholder pages are already on real data flows and did not require a fresh rewrite in this wave.

## Recommended next moves
1. Split `backend/app/services/pipelines_orchestrator.py` step handlers into focused modules while preserving imports.
2. Begin extracting a first compatibility-safe approvals/EDO/sign model module from `backend/app/models/models.py`.
3. Normalize approval/sign/EDO routes onto clearer canonical paths with shared provider policy guards.
4. Use the new route-group metadata to generate route-audit docs/tests automatically.
