# CODEX Wave Plan

_Date:_ 2026-03-22

## Plan for this wave
1. Perform a factual repo audit and refresh the audit docs before touching code.
2. Choose a safe, bounded hardening slice that improves enterprise reliability without rewriting working modules.
3. Reduce explicit stub behavior in the document/pipeline path while keeping API/task contracts backward-compatible.
4. Add focused regression tests and publish completion/gap/next-step artifacts.

## Executed in this wave
- Refreshed the repo audit with confirmed roots, route maps, deferred areas, risky compatibility pairs, and gap tracking against the super-TZ.
- Hardened `backend/app/services/pipelines_orchestrator.py` by replacing the most explicit stub step handlers with internal deterministic/projection handlers and provider-backed EDO dispatch.
- Hardened `backend/app/celery/tasks/document_jobs_required.py` so its compatibility wrappers now return explicit accepted/deferred bridge envelopes instead of raw `stub` statuses.
- Added targeted backend tests for the orchestrator dispatch path and the deferred task wrappers.

## Intentionally deferred
- Full decomposition of `backend/app/api/v1/router.py` and `backend/app/models/models.py` beyond documentation and compatibility analysis.
- Production adapters for approval/sign/EDO/1C/FRDO/EISOT.
- PWA plugin/service worker/offline queue/conflict UX.
- Cross-domain data-quality, attention-center, and universal timeline/task projections.

## Safe next moves
1. Split pipeline step handlers out of `pipelines_orchestrator.py` into focused modules while preserving imports.
2. Add explicit audit/event persistence for the new sign/EDO/index orchestration outputs.
3. Start extracting another compatibility-safe bounded model module from `backend/app/models/models.py`.
4. Consolidate approval/sign/EDO route families behind clearer canonical paths and shared provider policy guards.
