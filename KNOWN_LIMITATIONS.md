# KNOWN_LIMITATIONS

- **Updated on:** 2026-04-22
- **Owner:** Product Engineering + Platform
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Current limitations

| Limitation | Status | Evidence |
|---|---|---|
| Automatic inline chaining `generate -> apply_headers -> pdf` is not universal | partial | `scripts/branded_document_smoke.py`, generation pipeline docs/code paths |
| Branding asset selection is still ID-based (no dedicated media picker workflow) | partial | branding UI/API behavior, `GAP_REPORT.md` |
| Branded smoke script validates canonical stub pipeline only (not full tenant persistent media scenario) | partial | `scripts/branded_document_smoke.py` |
| Legacy duplicate path pairs remain on disk for compatibility (`docs/ADR` vs `docs/adr`, `modules/approval` vs `modules/approvals`) | partial | repository audit outputs + `scripts/repo_audit.py` |
| Frontend route-level chunking can still be improved as modules grow | partial | `frontend/vite.config.ts`, `npm --prefix frontend run build` |
| Notifications escalation/provider orchestration is not feature-complete | missing | `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py`, `GAP_REPORT.md` |
| Training/risk areas are foundations and should not be treated as fully closed | partial | module docs/code maturity notes in `GAP_REPORT.md` |
