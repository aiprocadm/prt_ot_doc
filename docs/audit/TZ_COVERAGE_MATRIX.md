# TZ_COVERAGE_MATRIX

| TZ area | Status | Canonical implementation |
|---|---|---|
| Structural audit / frontend-backend roots | Done | `README.md`, `docs/PROJECT_STRUCTURE.md`, `docs/audit/REPOSITORY_AUDIT.md`, `docs/audit/REPOSITORY_AUDIT.json`, `scripts/repo_audit.py`, `tests/test_repo_audit.py` |
| Canonical frontend root and `package.json` | Done | `frontend/package.json` |
| Python entrypoint compatibility | Done | `backend/app/main.py`, `app/__init__.py` |
| Branding profile inheritance | Done | `backend/app/modules/branding/service.py` |
| Header/footer requisites split (`header_details` / `footer_details`) | Done | `backend/app/modules/branding/schemas.py`, `frontend/src/pages/branding/BrandingSettingsPage.tsx` |
| Branch-branded header context (`branch_label` -> rendered headers) | Done | `backend/app/modules/branding/service.py`, `tests/api/test_branding_api.py` |
| Letterhead first/odd/even header/footer support | Done | `backend/app/modules/headers/engine.py` |
| Branding profile UI | Done | `frontend/src/pages/branding/BrandingSettingsPage.tsx` |
| Wizard organization/site/layout selection | Done | `frontend/src/pages/documents/DocumentsWizardPage.tsx` |
| Reproducibility metadata | Done | `backend/app/modules/branding/service.py` |
| Persisted wizard branding preview/history | Done | `frontend/src/stores/documentsWizard.ts` |
| Server-side branded generation history | Done | `backend/app/modules/branding/api.py`, `frontend/src/pages/branding/BrandingSettingsPage.tsx` |
| Apply-headers payload handoff | Done | `backend/app/modules/branding/api.py` |
| Branded document smoke command | Done | `scripts/branded_document_smoke.py`, `Makefile` |
| Full automatic apply-headers in every generation route | Partial | dedicated endpoint/job exists, not universally auto-chained |
| PDF / approval / archive continuation | Partial | foundation exists, depends on selected profile/orchestration |

| Notifications API boundary hardening | Done | `backend/app/api/routes/notifications.py`, `backend/app/modules/notifications/service.py`, `backend/app/modules/notifications/schemas.py`, `backend/tests/test_notifications_service.py` |
| Notification enum validation / structured 422 behavior | Done | `backend/app/modules/notifications/service.py`, `backend/app/api/error_handlers.py` |
| Training / LMS canonical doc | Done | `docs/TRAINING_AND_LMS.md` |
| Risk engine canonical doc | Done | `docs/RISK_ENGINE.md` |
| Acceptance scenarios canonical doc | Done | `docs/ACCEPTANCE_SCENARIOS.md` |
