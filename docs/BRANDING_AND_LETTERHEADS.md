# BRANDING_AND_LETTERHEADS

## Resolution hierarchy
1. `tenant.settings.branding`
2. `company.branding_payload`
3. `site.branding_payload`

## Supported branding profile fields
- full and short legal names;
- INN / KPP / OGRN;
- legal and actual addresses;
- phones / email / website;
- `header_details` for firm-blank requisites in page headers;
- logo / stamp / signature image file IDs;
- signatories;
- footer requisites and service notes;
- palette and watermark settings;
- preferred letterhead preset;
- arbitrary metadata for reproducibility and integrations.

## Preview endpoint
`POST /api/v1/branding/preview`

Returns:
- resolved profile;
- rendered `header_*` and `footer_*` sections;
- resolved watermark;
- unresolved placeholders;
- `apply_headers_payload` for the DOCX header/footer job;
- `wizard_defaults` for organization/site/preset carry-forward;
- resolution metadata (`scope_chain`, `effective_preset_source`, preset source diagnostics);
- reproducibility metadata including branding payload hash, header context hash, rendered section hash, preset content hash, and source entity timestamps.

## UI paths
- `/documents/branding` — maintain organization/site brand profile and preview letterheads.
- `/documents/wizard` step 5 — resolve company/site/preset, preview letterheads, inspect reproducibility metadata, and carry context into generation.

## Update semantics
- `PATCH /api/v1/branding/profile/{company_id}` is merge-based, not replace-based.
- `preferred_header_preset_code` is tenant-validated before save.
- branch-level `branch_label` overrides are reflected in preview and `apply_headers_payload`, so operators can issue branch-specific output without editing DOCX headers manually.
- Existing branding metadata and asset references remain intact when omitted from a partial patch.
