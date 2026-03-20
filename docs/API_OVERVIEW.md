# API_OVERVIEW

## Document core endpoints
- `GET /api/v1/branding/profile`
- `PATCH /api/v1/branding/profile/{company_id}`
- `POST /api/v1/branding/preview`
- `POST /api/v1/layout-presets`
- `GET /api/v1/layout-presets`
- `POST /api/v1/documents/generate`
- `POST /api/v1/documents/batch`
- `POST /api/v1/documents/{document_version_id}/apply-headers`

## Notes
- Branding preview is the canonical API for preparing firm-letterhead generation context.
- Header application remains idempotent and asynchronous.
