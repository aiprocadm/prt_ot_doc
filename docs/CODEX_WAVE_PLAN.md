# CODEX Wave Plan

_Date:_ 2026-03-21

## Prioritized backlog executed in this pass
1. **Repo audit + baseline docs.** Consolidate canonical entrypoints, active roots, placeholder maps, and compatibility risks in repo docs.
2. **Fat-router hardening without API breakage.** Extract route-registration topology from `backend/app/api/v1/router.py` into compatibility-safe grouped registries.
3. **Progressive mega-model decomposition.** Introduce narrower compatibility import layers for tenant/PPE ORM usage without moving table declarations.
4. **Static frontend -> real data conversions.** Replace placeholder operational pages with live tenant-aware data flows for PPE/Warehouse/Prescriptions/Audit Prep.
5. **Regression coverage and architecture docs.** Add focused tests and ADR/docs updates describing what changed and what remains deferred.

## Executed waves
### Wave A — Audit and baseline
- Refreshed `docs/CODEX_WAVE_AUDIT.md` with actual static/stub maps, risky areas, and route/model hot spots.
- Kept `scripts/repo_audit.py` output as supporting artifact, but elevated hand-written wave docs as the human-readable enterprise baseline.

### Wave B — Architectural hardening without breakage
- Introduced `backend/app/api/v1/route_groups.py` to centralize grouped route registrations.
- Updated `backend/app/api/v1/router.py` to delegate router inclusion to grouped registries while preserving all existing path contracts.
- Added progressive compatibility import modules for tenant/PPE model clusters instead of forcing new code to keep importing the mega-model directly.

### Wave C — Static-to-real operational pages
- `warehouse`: live PPE catalog and expiring issuance projection.
- `ppe`: live employee issuance cards from PPE + persons APIs.
- `prescriptions`: live prescriptions registry.
- `audit-prep`: live package projection derived from inspections + prescriptions + overdue tasks.

### Wave D — Verification and documentation
- Added frontend regression tests covering the new operational page flows.
- Updated architecture/static-to-real docs and created an ADR documenting the compatibility-safe decomposition pattern.

## Explicitly deferred, with reasons
- **True ORM module split** of `backend/app/models/models.py`: deferred to avoid breaking SQLAlchemy/Alembic imports in a broad undifferentiated move.
- **Dashboard tab conversion**: base summary is real, but task/document/readiness tabs still need backend projections rather than ad hoc aggregation.
- **Findings/corrective actions/fire safety/reference/settings**: still need live APIs or projection endpoints; not all have adequate existing backend contracts yet.
- **PWA/offline, data quality, attention center, workflow SLA timers**: left for next waves because they require deeper cross-module persistence and UX work.
