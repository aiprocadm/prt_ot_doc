# TZ_COVERAGE_MATRIX

| Area | Status | Canonical implementation |
|---|---|---|
| Structural audit / roots / entrypoints | Done | `README.md`, `docs/PROJECT_STRUCTURE.md` |
| Frontend root and `package.json` verification | Done | `frontend/package.json` |
| Branding profile inheritance | Done | `backend/app/modules/branding/service.py` |
| Letterhead first/odd/even sections | Done | `backend/app/modules/headers/engine.py` |
| Branding preview UX | Done | `frontend/src/pages/branding/BrandingSettingsPage.tsx` |
| Wizard organization/site/layout selection | Done | `frontend/src/pages/documents/DocumentsWizardPage.tsx` |
| Reproducibility metadata in preview | Done | `backend/app/modules/branding/service.py` |
| Apply-headers payload handoff | Done | `backend/app/modules/branding/api.py` |
| Full auto apply-headers inside every generation pipeline | Partial | dedicated job exists; not all generation paths auto-chain it |
| PDF/approval/archive continuation | Partial | foundational routes/modules exist; depends on selected pipeline profile |
