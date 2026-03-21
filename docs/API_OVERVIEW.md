# API_OVERVIEW

## Document core endpoints
- `GET /api/v1/branding/profile`
- `PATCH /api/v1/branding/profile/{company_id}`
- `GET /api/v1/branding/history`
- `POST /api/v1/branding/preview`
- `POST /api/v1/layout-presets`
- `GET /api/v1/layout-presets`
- `POST /api/v1/documents/generate`
- `POST /api/v1/documents/batch`
- `POST /api/v1/documents/{document_version_id}/apply-headers`

## Notes
- Branding preview is the canonical API for preparing firm-letterhead generation context.
- Header application remains idempotent and asynchronous.
- Branding profile patch calls are merge-based and preserve previously saved branding fields that are omitted in the current request.
- Branding profile payloads support split header/footer requisites and branch-level display-name overrides for letterheads.
- Invalid tenant-local layout preset references are rejected during branding profile updates with `404 Layout preset not found`.

## Notifications and cross-cutting contract notes
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/mark-read`
- `GET|PUT /api/v1/notifications/settings/me`
- `GET|PUT /api/v1/notifications/notification-settings/me`
- `GET|POST /api/v1/notifications/templates`
- `GET /api/v1/notifications/calendar/events`

Notification filter enums are now validated in an application service so invalid values return structured 422 payloads with `details.allowed_values` and `field_errors`.
