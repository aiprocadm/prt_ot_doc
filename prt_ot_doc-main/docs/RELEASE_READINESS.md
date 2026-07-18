# RELEASE READINESS

_Date:_ 2026-03-23

## Purpose
Canonical checklist for deciding whether the current branch is ready for enterprise rollout progression, staging promotion, or pilot cutover.

## Current corporate-readiness status
- **Foundation status:** strong modular-monolith base with real tenancy, authz primitives, document core, PWA packaging, billing, and workflow surfaces.
- **Current wave status:** targeted hardening landed for provider-mode diagnostics in integration readiness and for the authenticated `/api/pwa/bootstrap` contract.
- **Not yet release-complete for full enterprise rollout:** approval/sign/EDO mock-or-stub seams, platform-wide consistency normalization, operational workspace UX, and full offline conflict queue UX still require follow-up waves.

## Required checks before promotion
### Backend
```bash
pytest -q backend/tests/test_pwa_sync_bootstrap.py backend/tests/test_document_jobs_required.py backend/tests/test_corporate_readiness_hardening.py
python -m compileall backend/app/api/routes/pwa_sync.py backend/app/api/routes/integration_readiness.py
```

### Frontend
```bash
npm --prefix frontend run build
```

### Documentation
```bash
python - <<'PY'
from pathlib import Path
required = [
    'docs/CORPORATE_READINESS_AUDIT.md',
    'docs/CORPORATE_READINESS_PLAN.md',
    'docs/CORPORATE_READINESS_COMPLETION_REPORT.md',
    'docs/CORPORATE_READINESS_REMAINING_GAPS.md',
    'docs/CORPORATE_READINESS_NEXT_STEPS.md',
    'docs/RELEASE_READINESS.md',
]
missing = [item for item in required if not Path(item).exists()]
assert not missing, missing
print('ok')
PY
```

## Release gates
- Provider diagnostics must make non-production adapters explicit instead of silently looking production-ready.
- PWA bootstrap must remain authenticated, user-scoped, tenant-scoped, and rich enough to drive offline queue/conflict UX.
- Remaining stub/mock/deferred seams must be documented honestly in the corporate-readiness reports.
- Tests covering the above hardening must pass before merge or promotion.

## Known blockers for full enterprise GA
- `backend/app/api/routes/ws_stub.py` remains deferred.
- `backend/app/api/routes/approval_signing_v1.py`, `backend/app/api/routes/approval_orchestration.py`, and `backend/app/api/routes/edo_workflow.py` still expose non-production semantics in critical orchestration paths.
- Frontend field UX still needs local offline queue screens, retry/resume flows, and conflict-resolution UI.
