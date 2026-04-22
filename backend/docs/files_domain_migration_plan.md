# Files domain migration plan (single canonical layer)

## Decision

- **Canonical API layer:** `app.modules.files.api` (`backend/app/modules/files/api.py`).
- **Canonical data layer for files endpoints:** `app.modules.files.models` (`FileRecord`, `FileVersion`, `FileLink`, ...).
- **Legacy layer (deprecated):** `app.api.routes.files` + `app.models.file` for endpoint evolution.

## What is changed now

1. In `backend/app/api/v1/route_groups.py` only one `/files` router is registered.
2. `/files` now points only to `app.modules.files.api`.
3. Legacy endpoint module `backend/app/api/routes/files.py` is explicitly marked as deprecated for new development.
4. Legacy model module `backend/app/models/file.py` is explicitly marked as deprecated for new file API work.

## Canonical vs compatibility-only endpoint paths

All endpoints below are hosted on `/api/v1/files`.

### Canonical endpoints

- `POST /api/v1/files:upload-init`
- `POST /api/v1/files:upload-complete`
- `GET /api/v1/files/{file_id}/versions/{version_id}:download-url`
- `POST /api/v1/files/presign-upload`
- `POST /api/v1/files/complete-upload`
- `POST /api/v1/files/{file_id}:finalize`
- `GET /api/v1/files/records/{file_id}`
- `POST /api/v1/files/{file_id}:reindex`
- `GET /api/v1/files/{file_id}/download-url`
- `POST /api/v1/files/{file_id}:link`
- `GET /api/v1/files/entities/{entity_type}/{entity_id}/files`
- `POST /api/v1/files/{file_id}:signed-url`
- `DELETE /api/v1/files/{file_id}/link/{link_id}`
- `POST /api/v1/files/abort-upload`
- `POST /api/v1/files/upload-multipart`
- `GET /api/v1/files`
- `POST /api/v1/files/{file_id}/new-version`
- `GET /api/v1/files/{file_id}/versions`
- `DELETE /api/v1/files/{file_id}`

### Compatibility-only aliases (legacy-compat)

- `POST /api/v1/files/init-upload` → canonical `POST /api/v1/files/presign-upload`
- `POST /api/v1/files/complete-upload-v2` → canonical `POST /api/v1/files/complete-upload`
- `POST /api/v1/files/{file_id}:complete` → canonical `POST /api/v1/files/{file_id}:finalize`
- `POST /api/v1/files/{file_id}:download-url` → canonical `GET /api/v1/files/{file_id}/download-url`
- `POST /api/v1/files/{file_id}/link` → canonical `POST /api/v1/files/{file_id}:link`
- `GET /api/v1/files/entities/{entity_type}/{entity_id}/list` → canonical `GET /api/v1/files/entities/{entity_type}/{entity_id}/files`
- `POST /api/v1/files/{file_id}/signed-url` → canonical `POST /api/v1/files/{file_id}:signed-url`

## Remaining legacy router migration work

- ⏳ Legacy `POST /api/v1/files-legacy/upload` should be moved to upload-init/upload-complete flow for all clients.
- ⏳ Legacy `GET /api/v1/files-legacy/{file_id}` should migrate to `GET /api/v1/files/records/{file_id}`.

## Follow-up implementation phases

1. **Client migration:** switch internal/external callers from legacy `/files-legacy/upload` and `/files-legacy/{file_id}` to canonical endpoints.
2. **Contract freeze:** once traffic is cut over, return `410 Gone` on legacy endpoints (temporary), then remove module.
3. **Model convergence:** progressively migrate remaining business flows still tied to `app.models.file.File` to `app.modules.files.models.FileRecord` where applicable.
4. **DB/migrations cleanup:** remove unused legacy columns/tables only after all readers/writers are migrated.
5. **Test cleanup:** keep only canonical files API tests and remove legacy endpoint expectations.
