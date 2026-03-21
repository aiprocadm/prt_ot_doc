# RELEASE_READINESS

## Current status
- Template upload, version history, lint and preview are implemented foundations.
- Owner bootstrap and access issuance are reproducible from repo scripts/docs.
- Document generation for organization-specific flows is available and can be combined with site/branch metadata and branding/header-footer stages.

## Before production cutover
- verify migrations on target DB;
- verify storage + LibreOffice + ClamAV + Celery workers;
- run backend/frontend smoke for custom template upload and document generation;
- provision real owner/demo credentials outside git.
