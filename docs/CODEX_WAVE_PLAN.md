# CODEX Wave Plan

_Date:_ 2026-03-22

## Strategy for this wave
1. Audit the repo first and refresh factual documentation.
2. Improve one backend seam and one frontend platform seam without rewriting working modules.
3. Keep API/task contracts backward-compatible.
4. Add targeted tests and update wave completion artifacts.

## Executed in this wave
- Refreshed the repository audit and plan docs based on actual code state.
- Hardened `backend/app/celery/tasks/document_jobs_required.py` so report export / integration sync compatibility tasks can use named internal runtime bridges while preserving compatibility envelopes when no bridge is configured.
- Added a real PWA baseline in `frontend/vite.config.ts` with manifest/service worker generation and runtime registration in `frontend/src/pwa/register.ts`.
- Added/updated focused tests around background bridge behavior and frontend build verification.

## Why this slice was chosen
- It addresses two explicitly confirmed gaps from the audit.
- It does not break existing public routes or task names.
- It improves platform hardening while leaving room for deeper future decomposition.

## Intentionally deferred
- Massive refactors of `router.py`, `models.py`, and `pipelines_orchestrator.py`.
- Production provider adapters for approval/sign/EDO and external integrations.
- Full offline queue/conflict UX and attention/data-quality centers.

## Recommended next moves
1. Continue extracting canonical submodules from `backend/app/models/models.py`.
2. Introduce concrete internal handlers for report export and integration sync to consume the new compatibility bridge seam.
3. Expand PWA support from installable shell to tenant-aware offline queue, sync status, retries, and conflict resolution.
4. Perform endpoint-by-endpoint tenant/authz/audit/correlation review.
