# RELEASE_READINESS

## Ready now
- Canonical roots and active entrypoints are documented.
- `frontend/package.json` is verified in the actual frontend root.
- Tenant/company/site branding inheritance works through the backend branding module.
- Header/footer requisites can be managed independently through `header_details` and `footer_details`.
- Branch-specific branded names are reflected in generated header/footer context.
- Wizard step 5 exposes branded preview, resolution chain, watermark diagnostics, and reproducibility snapshot.
- Branded preview metadata is durable across wizard navigation through the persisted wizard store.
- Backend tests and repo-local smoke checks cover the branding preview/apply-headers handoff.
- Tenant bootstrap with owner user.
- Dev admin bootstrap.
- Demo tenant bootstrap.
- Custom template catalog + version upload + lint + preview.
- Company-aware document generation.
- Metadata-backed scope visualization for tenant/company/site templates.
- Canonical docs for next-wave continuation from repo.
- Template API/UI contract is again parseable and coherent for custom upload/version/scope flows.

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

## Launch readiness verdict (2026-03-25)
- Status: NOT READY (no-go for production cutover now).
- Why: there are still high/medium enterprise gaps outside the completed Wave A/B slices (action-level permission coverage, unified task projection breadth, data quality module, offline field scenarios, reliability runbooks and worker-level operational checks).
- Ready-to-launch trigger: switch to READY only after production cutover checklist passes on target infra and remaining high-severity operational gaps are either closed or explicitly risk-accepted by owners.
