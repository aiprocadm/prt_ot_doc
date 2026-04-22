# KNOWN_LIMITATIONS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Product Engineering + Platform
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Current limitations

| Limitation | Status | Test evidence | Workflow evidence | Script evidence | Doc evidence |
|---|---|---|---|---|---|
| Automatic inline chaining `generate -> apply_headers -> pdf` is not universal | `partial` | branded flow tests (partial) | `.github/workflows/ci.yml` | `scripts/branded_document_smoke.py` | generation pipeline docs/code paths |
| Branding asset selection is still ID-based (no dedicated media picker workflow) | `partial` | branding API tests (partial functional scope) | `.github/workflows/ci.yml` | — | branding UI/API behavior, `GAP_REPORT.md` |
| Branded smoke script validates canonical stub pipeline only (not full tenant persistent media scenario) | `partial` | smoke-level only | `.github/workflows/ci.yml` | `scripts/branded_document_smoke.py` | `GAP_REPORT.md` |
| Legacy duplicate path pairs remain on disk for compatibility (`docs/ADR` vs `docs/adr`, `modules/approval` vs `modules/approvals`) | `partial` | `tests/test_repo_audit.py` | `.github/workflows/ci.yml` | `scripts/repo_audit.py` | repository audit outputs |
| Frontend route-level chunking can still be improved as modules grow | `partial` | frontend build/test signal | `.github/workflows/ci.yml` | `npm --prefix frontend run build` | `frontend/vite.config.ts` |
| Notifications escalation/provider orchestration is not feature-complete | `missing` | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py` (coverage does not close full orchestration scope) | `.github/workflows/ci.yml` | — | `GAP_REPORT.md` |
| Training/risk areas are foundations and should not be treated as fully closed | `partial` | readiness checks (partial) | `.github/workflows/ci.yml` | `python scripts/pilot_readiness.py` | module docs and maturity notes in `GAP_REPORT.md` |

## Cross-links

- Plan tracker: `docs/stabilization/PLAN.md`
- Acceptance matrix: `ACCEPTANCE_TEST_MATRIX.md`
- Gap report: `GAP_REPORT.md`
- Release readiness verdict: `RELEASE_READINESS.md`
