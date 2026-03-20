# TZ_COVERAGE_MATRIX

| TZ area | Status | Canonical implementation |
|---|---|---|
| Structural audit / frontend-backend roots | Done | `README.md`, `docs/PROJECT_STRUCTURE.md` |
| Canonical frontend root and `package.json` | Done | `frontend/package.json` |
| Python entrypoint compatibility | Done | `backend/app/main.py`, `app/__init__.py` |
| Branding profile inheritance | Done | `backend/app/modules/branding/service.py` |
| Letterhead first/odd/even header/footer support | Done | `backend/app/modules/headers/engine.py` |
| Branding profile UI | Done | `frontend/src/pages/branding/BrandingSettingsPage.tsx` |
| Wizard organization/site/layout selection | Done | `frontend/src/pages/documents/DocumentsWizardPage.tsx` |
| Reproducibility metadata | Done | `backend/app/modules/branding/service.py` |
| Persisted wizard branding preview/history | Done | `frontend/src/stores/documentsWizard.ts` |
| Apply-headers payload handoff | Done | `backend/app/modules/branding/api.py` |
| Full automatic apply-headers in every generation route | Partial | dedicated endpoint/job exists, not universally auto-chained |
| PDF / approval / archive continuation | Partial | foundation exists, depends on selected profile/orchestration |
