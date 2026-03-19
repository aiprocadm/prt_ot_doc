# TZ coverage matrix

| Area | Status | Canonical implementation | Verification |
| --- | --- | --- | --- |
| Structural audit / roots / entrypoints | Done | `backend/`, `frontend/`, `frontend/package.json`, `backend/app/main.py` | manual audit + docs refresh |
| Branded org + branch profile | Done | `backend/app/modules/branding/*` | `pytest -q tests/api/test_branding_api.py` |
| Header/footer first/odd/even | Done | `backend/app/modules/headers/engine.py` | `pytest -q tests/headers/test_engine.py` |
| Watermark resolution + reproducibility | Done | `backend/app/modules/branding/service.py` | `pytest -q tests/api/test_branding_api.py` |
| Frontend branding UI | Done | `frontend/src/pages/branding/BrandingSettingsPage.tsx` | `npm --prefix frontend run typecheck` |
| Layout preset editor | Done | `frontend/src/components/LayoutPresetEditor/LayoutPresetEditor.tsx` | `npm --prefix frontend run typecheck` |
| README / canonical docs | Done | `README.md`, `docs/*.md` | manual review |
| Full browser e2e branded generation | Partial | existing pipeline modules preserved | backlog / next wave |
