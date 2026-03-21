# DOCUMENT_CORE

## Canonical modules
- Templates: `backend/app/modules/templates/`, `backend/app/api/v1/router.py`.
- Document generation: `backend/app/api/routes/documents.py`, `backend/app/tasks.py`.
- Header/footer: `backend/app/modules/headers/`.
- Replace: `backend/app/modules/replace/`.
- PDF: `backend/app/modules/pdf/` + celery tasks.
- Document passport: `backend/app/modules/templates/service.py`, `backend/app/modules/doc_render/passport.py`, `backend/app/core/utils/pdf_passport.py`.

## Implemented building blocks
- tenant/company/site branding inheritance;
- branch/site branding overrides feed the effective branch display name used in header/footer rendering;
- first / odd / even header and footer sections;
- placeholder rendering with unresolved-placeholder reporting;
- watermark resolution from preset + profile + request override;
- explicit `header_details` + `footer_details` fields for stable letterhead requisites;
- reproducibility metadata for branding payload, header context, rendered sections, preset content, and entity timestamps;
- async idempotent header application endpoint and Celery job;
- frontend wizard handoff using backend-returned `apply_headers_payload`.
## Current state after audit
### Implemented
- template catalog;
- template versions;
- DOCX upload;
- lint + preview;
- async generation jobs;
- document snapshots / passport / reproducibility hashes;
- PDF conversion foundation;
- approval/sign/EDO integration points;
- document status/release widgets in frontend.

### Hardened in this wave
- catalog API now exposes normalized template scope and category metadata;
- template version upload now correctly links `current_version_id`;
- template selection for generation is tolerant to historical `code` vs `name` inconsistencies;
- docs now explicitly describe demo/owner/bootstrap/user-access flows.

### Still partial
- fully automatic chain `template -> headers -> replace -> pdf -> approval` is not universal for every route;
- version diff and visual preview are not yet enterprise-complete;
- template scope indexing remains metadata-based rather than dedicated relational filters.
## Current boundary
Preview preparation and apply-headers handoff are production-ready. Some generation profiles still require explicit chaining of `apply_headers` after DOCX creation rather than automatic inline chaining in every flow.

## Custom template note
- canonical upload/versioning/scope contract is documented in `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`;
- branch-specific template work uses backend `Site` as the concrete branch/facility entity;
- template DTOs now surface `scope`, `template_type`, `current_version`, and `versions` to keep backend/frontend contracts aligned for operator workflows.
