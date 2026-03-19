# TZ coverage matrix

| Area | Status | Canonical implementation | Verification |
| --- | --- | --- | --- |
| Structural audit / roots | Done | `backend/`, `frontend/`, `frontend/package.json`, `backend/app/main.py` | manual audit + docs refresh |
| Branded org profile | Done (company/site persistence) | `backend/app/modules/branding/*` | `tests/api/test_branding_api.py` |
| Header/footer first/odd/even | Done | `backend/app/modules/headers/engine.py` | `tests/headers/test_engine.py` |
| Frontend branding UI | Done | `frontend/src/pages/branding/BrandingSettingsPage.tsx` | `npm --prefix frontend run build` |
| README / canonical docs | Done | `README.md`, `docs/*.md` | manual review |
| Broader critical scenarios | Partial | existing modules preserved | existing regression suites |
