# CHANGED_PATHS_AND_RENAMES

## Canonical paths reaffirmed in this wave
- `backend/` remains the canonical backend root.
- `frontend/` remains the canonical frontend root.
- `frontend/package.json` remains the only active frontend package manifest.
- `backend/app/main.py` remains the ASGI entrypoint.
- `backend/app/api/app.py` remains the FastAPI app factory.

## Compatibility paths left in place intentionally
- `app/__init__.py` remains a compatibility shim so legacy `app.*` imports continue to resolve to `backend/app`.
- `docs/ADR/` and `docs/adr/` both still exist. New ADRs should be added under `docs/ADR/`; lowercase `docs/adr/` should be treated as historical legacy content.
- `backend/app/modules/approval/` and `backend/app/modules/approvals/` both still exist. New approval work should target the plural `approvals` path.

## Structural/doc changes in this wave
- Rebuilt `scripts/repo_audit.py` into a single canonical implementation after merge corruption, so the generated audit report once again captures canonical entrypoints, config inventory, repo-root directories, root expectations, required docs coverage, and legacy path guidance in both Markdown and JSON formats.
- Added `docs/WORKFLOWS_AND_EVENTS.md` as the canonical workflow/event map.
- Added `docs/OBSERVABILITY.md` as the canonical health/metrics/logging/tracing reference.
- Canonicalized testing documentation to `docs/TESTING.md` and reduced `docs/testing.md` to a compatibility pointer.
- Updated build configuration in `frontend/vite.config.ts` to split vendor bundles more predictably for production builds.
- Normalized `docs/README.md` to point to the canonical uppercase docs (`PROJECT_STRUCTURE.md`, `TESTING.md`, `SETUP.md`, `BACKEND.md`, `FRONTEND.md`) instead of legacy lowercase aliases.
- Tightened the persisted document wizard branding-preview history so repeated previews of the same reproducibility snapshot do not create duplicate continuity entries.
- Simplified `tests/test_repo_audit.py` into a single coherent test module and removed merge-style duplication from the repository-audit acceptance evidence.

## Rename policy going forward
- Prefer documenting canonical paths and deprecating legacy paths before performing risky repo-wide moves.
- Keep compatibility shims only when they protect existing imports, tooling, or operator commands.
- Record every future rename/move here and in `docs/PROJECT_STRUCTURE.md`.
