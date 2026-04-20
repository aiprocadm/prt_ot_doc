# File hardening inventory, threat model, and rollout guidance

## Scope and inventory

### Upload / import entry points

1. Legacy direct upload (multipart body streamed through API process):
   - `POST /files/upload` and `POST /files/upload-template` in `backend/app/api/routes/files.py`.
   - Implementation path: `_ingest_upload(...)` → `_persist_and_audit(...)` → `enqueue_scan_request(...)`.
2. Canonical pre-signed upload session flow:
   - `POST /api/v1/files:upload-init`, `POST /api/v1/files/presign-upload`, `POST /api/v1/files/init-upload`, `POST /api/v1/files/{file_id}/new-version`.
   - Implementation path: `backend/app/modules/files/api.py` → `FileService.create_upload_session(...)` / `create_new_version_upload_session(...)`.
3. Compatibility multipart upload flow:
   - `POST /api/v1/files/upload-multipart` in `backend/app/modules/files/api.py`.
   - Uploads bytes to object storage then finalizes+scans.

### Download / preview / export entry points

1. Legacy download URL issue:
   - `GET /files/{file_id}/download` in `backend/app/api/routes/files.py`.
2. Canonical download URL issue:
   - `GET|POST /api/v1/files/{file_id}/download-url`,
   - `POST /api/v1/files/{file_id}:signed-url`,
   - `GET /api/v1/files/{file_id}/versions/{version_id}:download-url`.
3. Read metadata/list paths that expose object identifiers:
   - `GET /files/{file_id}`,
   - `GET /api/v1/files/records/{file_id}`,
   - `GET /api/v1/files`,
   - `GET /api/v1/files/entities/{entity_type}/{entity_id}/files`,
   - `GET /api/v1/files/{file_id}/versions`.

### Replace/delete paths

1. Legacy delete:
   - `DELETE /api/v1/files/{file_id}`.
2. Link removal (detaches object from entity):
   - `DELETE /api/v1/files/{file_id}/link/{link_id}`.
3. Abort upload:
   - `POST /api/v1/files/abort-upload`.

### Background tasks touching file objects

1. `files.av_scan_file_job` (`backend/app/modules/files/tasks.py`): performs AV scan and state update.
2. `files.purge_temp_files` (`backend/app/modules/files/tasks.py`): soft-deletes stale temp objects.
3. `FileService.finalize_upload(...)` / `FileService.av_scan_file(...)` trigger async jobs:
   - `av_scan_file_job.delay(...)`,
   - `index_file_content_job.apply_async(...)`.
4. Legacy scan flow in `backend/app/api/routes/files.py`:
   - `enqueue_scan_request(ClamAVScanRequest(...))`.

## Control verification matrix

## 1) Extension + MIME + magic validation

- Legacy direct upload path performs content sniffing and extension checks via:
  - `guess_mime_type(...)` (header + libmagic/sample + filename),
  - `_ensure_allowed_mime(...)`,
  - `determine_extension(...)` + expected/provided extension comparison,
  - rejection on mismatch (`FILE_EXTENSION_MISMATCH`) and disallowed extension (`UNSUPPORTED_FILE_EXTENSION`).
- Canonical pre-signed flow validates declared content type against `settings.file_allowed_mime`.
- Gap: pre-signed flow cannot inspect bytes pre-upload; AV+post-upload validation remains authoritative.

## 2) Double-extension rejection

- Added explicit rejection in `FileService.create_upload_session(...)` and `create_new_version_upload_session(...)`:
  - denies filenames where an allowed document extension is followed by a dangerous trailing executable/script extension (e.g., `statement.pdf.exe`).

## 3) Filename/path sanitization

- `storage.build_tenant_key(...)`: strips `..` and `/` in filename segment.
- `service._safe_filename(...)`: strips traversal and path separators for persisted original names.
- `storage.assert_tenant_key(...)`: enforces per-tenant key prefixes and blocks traversal markers (`../`, `..\\`).

## 4) Size limits

- Enforced on both legacy streamed uploads and pre-signed session creation:
  - `settings.max_upload_size`,
  - returns 413 on overflow (`FILE_TOO_LARGE` / `max_upload_size_exceeded`).

## 5) Tenant-aware object keys

- Canonical key builders namespace by tenant:
  - `tenants/{tenant}/...`.
- Tenant ownership checks on read/complete/download:
  - `enforce_row_belongs_to_tenant(...)`,
  - `storage.assert_tenant_key(...)`.

## 6) Authz on read/replace/delete

- Legacy route includes ABAC role checks (`_FILE_UPLOAD_ROLES`, `_FILE_READ_ROLES`) plus company-level guards.
- Canonical module currently relies primarily on tenant scoping and object ownership checks.
- Delete operations are tenant-scoped (`FileService.delete_file`).
- Recommendation: extend canonical module endpoints with explicit ABAC dependencies to match legacy guarantees.

## 7) Signed URL TTL policy

- Canonical signed download TTL is clamped to `[60, 900]` in `FileService.get_signed_download_url(...)`.
- Schema-level TTL guardrails:
  - `SignedUrlRequest.ttl_seconds` and `DownloadUrlRequest.ttl_seconds` enforce `ge=60, le=900`.
- Legacy `download` uses configured TTL (`settings.presign_download_ttl_seconds`).

## 8) Safe content-disposition / nosniff / cache

- Legacy presign sets `ResponseContentDisposition=attachment` and `ResponseContentType` in presigned headers.
- `nosniff` and cache-control are not consistently enforced from API layer for object responses (depends on S3/object-store metadata and edge/gateway policy).
- Recommendation:
  1. enforce `X-Content-Type-Options: nosniff` at API gateway,
  2. enforce conservative cache policy (`private, max-age=...` or `no-store`) by object class,
  3. centrally template content-disposition for all download surfaces.

## Active-content policy & quarantine transitions

### Current policy state

- Explicitly blocked by filename/content policy:
  - macro-enabled Office docs: `.docm`, `.xlsm` (pre-signed session flow),
  - dangerous double extension ending in executable/script type.
- Potentially active types such as HTML/SVG/JS are blocked when excluded from `settings.file_allowed_mime` / extension lists.
- AV is required gate for download in legacy path (`record.is_quarantined`/scan status check) and in canonical path (`status == clean` required).

### Quarantine/state transitions

1. Upload created:
   - legacy: `is_quarantined=True`, `scan_status=PENDING`,
   - canonical: `status=uploading/uploaded`.
2. Finalization:
   - canonical sets `status=scanning`.
3. AV result:
   - clean → `clean/ready`,
   - infected → `infected` or `quarantined` (version flow),
   - scanner error/unavailable → remains non-downloadable (`scanning` / error metadata).
4. Download allowed only for clean-ready objects.

## Threat model summary

### Primary threats

1. Malicious content upload (executable/macro/script payloads).
2. MIME/extension confusion (polyglot files, spoofed types).
3. Path traversal / key-confusion across tenants.
4. Unauthorized read/delete/link operations.
5. Long-lived URL leakage and replay.
6. Active-content rendering in browser context (inline HTML/SVG/JS).

### Existing mitigations

- Allowlist MIME/extensions, extension-mismatch checks, AV scan gating.
- Tenant-key assertion + row-level tenant checks.
- TTL bounded signed URLs.
- Audit/download logging.

### Remaining hardening tasks (recommended)

1. Add ABAC checks to canonical module routes to align with legacy route security.
2. Introduce centralized active-content denylist independent of config drift.
3. Enforce object response headers (`nosniff`, strict disposition/cache policy) at gateway/storage metadata layer.
4. Add one-way quarantine workflow for infected content with operator-only override.

## Rollout & operations guidance

## Phase 1 (safe defaults)

1. Deploy new double-extension rejection + negative tests.
2. Publish allowed MIME/extension matrix to platform config docs.
3. Confirm presign TTL configuration within 60-900 seconds.

## Phase 2 (enforcement parity)

1. Add ABAC dependencies to canonical files endpoints.
2. Add explicit policy for preview endpoints (disable inline render for active content).
3. Ensure tenant audit logs include all delete/download denial reasons.

## Phase 3 (operational controls)

1. Security monitoring:
   - alert on spikes in `unsupported_content_type`, `dangerous_double_extension`, AV infected detections, and cross-tenant denies.
2. Incident response:
   - quarantine infected objects, revoke outstanding URLs by shortening TTL + object key rotation if needed.
3. Backfill and clean-up:
   - run periodic scans/index consistency checks for legacy objects uploaded before policy hardening.
