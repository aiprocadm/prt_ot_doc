# CODEX Wave Next Steps

_Date:_ 2026-03-22

## Recommended next implementation slice
1. Extract dedicated pipeline step handler modules for render/sign/EDO/index/archive behavior and keep `PipelineOrchestrator` as a coordinator.
2. Add audit log and outbox/event coverage for the newly hardened sign/EDO/index operations.
3. Decompose one more bounded area out of `backend/app/models/models.py` using compatibility imports.
4. Consolidate approval/sign/EDO route families and document canonical vs compatibility paths.
5. Start real PWA wiring in `frontend/vite.config.ts` with manifest/service worker/offline shell as an honest v1 baseline.

## Validation priorities for the next wave
- tenant isolation and authz;
- document chain and readiness behavior;
- workflow/sign/EDO transitions;
- offline sync edge cases;
- placeholder-to-real UI regressions where new projections are introduced.
