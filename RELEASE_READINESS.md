# RELEASE_READINESS

## Ready now
- Tenant bootstrap with owner user.
- Dev admin bootstrap.
- Demo tenant bootstrap.
- Custom template catalog + version upload + lint + preview.
- Company-aware document generation.
- Metadata-backed scope visualization for tenant/company/site templates.
- Canonical docs for next-wave continuation from repo.

## Not fully closed
- Full enterprise lifecycle automation for every document path.
- Dedicated branch model separate from `Site`.
- Fully relational template scope filtering/reporting.
## Current status
- Template upload, version history, lint and preview are implemented foundations.
- Owner bootstrap and access issuance are reproducible from repo scripts/docs.
- Document generation for organization-specific flows is available and can be combined with site/branch metadata and branding/header-footer stages.

## Before production cutover
- verify migrations on target DB;
- verify storage + LibreOffice + ClamAV + Celery workers;
- run backend/frontend smoke for custom template upload and document generation;
- provision real owner/demo credentials outside git.
