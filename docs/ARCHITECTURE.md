# Architecture

## Style
- Modular monolith.
- FastAPI API layer with thin routers and domain/application services.
- Tenant-aware middleware and RBAC/ABAC guards remain mandatory.
- Async background execution for heavy document jobs through Celery-compatible tasks.

## Canonical paths
- API factory: `backend/app/api/app.py`
- V1 router composition: `backend/app/api/v1/router.py`
- Document headers engine: `backend/app/modules/headers/engine.py`
- Branding orchestration: `backend/app/modules/branding/service.py`
- Frontend document wizard: `frontend/src/pages/documents/DocumentsWizardPage.tsx`
- Frontend branding screen: `frontend/src/pages/branding/BrandingSettingsPage.tsx`

## Document core architecture
`Template -> branding profile -> layout preset -> header/footer rendering -> replace -> PDF -> approval/sign/archive`

Branding data is resolved with inheritance:
1. `Tenant.settings.branding`
2. `Company.branding_payload`
3. `Site.branding_payload`

The effective context is rendered into layout preset placeholders before the downstream document pipeline continues.
