# CODEX Wave Plan

_Date:_ 2026-03-21

## Prioritized backlog for this implementation pass
1. Capture a factual audit baseline in repo docs.
2. Replace one confirmed placeholder page with real data flow without backend breakage.
3. Add tests documenting the page conversion and protecting regressions.
4. Record follow-up decomposition and enterprise-hardening items for the next waves.

## Executed scope
### Wave A1 — Baseline audit and planning
- Added `docs/CODEX_WAVE_AUDIT.md`.
- Added `docs/CODEX_WAVE_PLAN.md`.

### Wave A2 — Frontend static-to-real conversion
- Convert `CRM / Финансы` from hardcoded demo rows to live tenant-scoped API data.
- Reuse existing backend finance endpoints rather than inventing new compatibility-risky APIs.
- Add loading, error, empty, and search states.
- Keep existing route and permission contract intact.

### Wave A3 — Regression coverage
- Add focused frontend tests for successful load, empty state, and filtering.

## Deferred next-wave items
- Compatibility-safe decomposition of `backend/app/api/v1/router.py` into route registries.
- Compatibility-safe model split for `backend/app/models/models.py`.
- Static-to-real conversion for `warehouse`, inspection prep, audit prep, dashboard variants, and other registry pages.
- Full tenancy/authz consistency sweep and acceptance matrix refresh.
- Document-core readiness/dependency and task/timeline expansion.
