# BRANDING_AND_LETTERHEADS

## Scope hierarchy
1. Tenant defaults from `tenant.settings.branding`
2. Company branding payload
3. Site branding payload

## Supported profile fields
- legal and short names
- INN/KPP/OGRN
- legal/actual address
- phones/email/website
- logo/stamp/signature file ids
- palette and watermark settings
- footer requisites and service notes
- signatories and metadata
- preferred letterhead preset

## Preview API
`POST /api/v1/branding/preview`

Returns:
- resolved profile;
- resolution metadata (`scope_chain`, `effective_preset_source`, presence of company/site branding layers);
- rendered sections (`header_first`, `header_odd`, `header_even`, `footer_*`);
- resolved watermark;
- reproducibility metadata;
- stable `branding_payload_hash` for reproducible reruns and audit comparison;
- `apply_headers_payload` ready to pass into header application flow;
- `wizard_defaults` for UI generation flows.

## Update semantics
- `PATCH /api/v1/branding/profile/{company_id}` validates `preferred_header_preset_code` inside the current tenant before saving.
- Branding updates merge into the existing company/site payload instead of replacing the whole JSON blob. This preserves logos, stamps, metadata and prior requisites during partial edits from UI or API clients.

## UI path
- Settings: `/documents/branding`
- Wizard preview: `/documents/wizard` step 5
