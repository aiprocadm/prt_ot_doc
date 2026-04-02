# ADR-2026-03-21: Compatibility-safe route registry and model split scaffolding

## Status
Accepted

## Context
The repository has two explicit structural hotspots:
- `backend/app/api/v1/router.py` had become both the router composition root and an implementation bucket.
- `backend/app/models/models.py` remains a mega-model file whose abrupt split would risk breaking imports, SQLAlchemy metadata registration, and Alembic expectations.

The project requirement for this wave was *enterprise hardening without breakage*, not a rewrite.

## Decision
1. Introduce `backend/app/api/v1/route_groups.py` as the canonical grouped router-registration layer.
2. Keep `backend/app/api/v1/router.py` as the public compatibility composition root, but make it delegate route-group assembly.
3. Introduce narrow compatibility modules (`backend/app/models/tenanting.py`, `backend/app/models/ppe_registry.py`) that re-export stable subsets from `app.models.models`.
4. Move new or updated imports gradually toward these smaller modules before attempting any physical table-definition relocation.

## Consequences
### Positive
- Route composition becomes easier to audit by bounded group without changing any HTTP paths.
- The mega-model can be decomposed progressively by import migration first, then table-definition extraction later.
- Future waves have a documented, low-risk pattern to continue decomposition.

### Negative / deferred
- The mega-model still exists and remains the source of SQLAlchemy table declarations for now.
- Some route-group definitions still point to dense endpoint modules; additional thinning is still needed.
- This ADR does not itself solve workflow/PWA/data-quality maturity gaps.
