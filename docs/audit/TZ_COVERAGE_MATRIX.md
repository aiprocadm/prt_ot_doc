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
| Custom template scope/type DTO alignment | Done | `backend/app/api/v1/router.py`, `backend/app/modules/templates/schemas.py`, `frontend/src/types/dto/templates.ts` |
| Template upload/version/lint/preview canonical doc | Done | `docs/TEMPLATE_UPLOAD_AND_RENDERING.md` |
| Demo access canonical doc | Done | `docs/DEMO_ACCESS.md` |
| Owner bootstrap/access canonical doc | Done | `docs/OWNER_ADMIN_ACCESS.md` |
| User role issuance and scope assignment doc | Done | `docs/USER_ACCESS_AND_ROLES.md` |

## Waves 3–5 (TZ rollout) — incremental implementation

| TZ area | Status | Canonical implementation |
|---|---|---|
| Cross-domain link: signed document → universal task | Done | `backend/app/services/domain_hooks.py`, `backend/app/services/documents.py`, `tests/services/test_domain_hooks_document_signed.py` |
| EDO production HTTP adapter (config-gated) | Done | `backend/app/services/integrations/http_edo.py`, `backend/app/services/integrations/factory.py`, `backend/app/core/config.py`, `docs/integrations/PRODUCTION_ADAPTERS.md`, `tests/services/test_edo_integration_factory.py` |
| Role-based workspace UX: attention + data quality hubs | Done | `frontend/src/pages/workspace/*`, `frontend/src/router/routeGroups.tsx`, `frontend/src/components/layout/SideNav.tsx` |
| Offline / sync conflict operator guidance | Done | `frontend/src/pages/help/SyncConflictHelpPage.tsx`, route `/help/sync-conflicts` |
| Acceptance traceability (Wave 3–5 slice) | Done | `ACCEPTANCE_TEST_MATRIX.md` (section below), this table |
