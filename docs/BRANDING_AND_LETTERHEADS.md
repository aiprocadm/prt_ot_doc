# Branding and letterheads

## Supported profile attributes
- Legal/short name
- INN/KPP/OGRN, legal/actual address
- Email, phones, footer requisites
- Preferred letterhead preset
- Watermark text and enable flag
- Contact/signatory blocks
- Tenant/company/site inheritance

## API
- `GET /api/v1/branding/profile?company_id=...&site_id=...`
- `PATCH /api/v1/branding/profile/{company_id}`
- `POST /api/v1/branding/preview`
- `POST /api/v1/layout-presets`
- `POST /api/v1/documents/{document_version_id}/apply-headers`

## UI
- Branding settings: `/documents/branding`
- Layout preset editor: `/admin/layout-presets`

## Operational flow
1. Choose company/branch.
2. Maintain canonical requisites in branding profile.
3. Bind preferred preset code.
4. Preview generated header/footer.
5. Use the same preset code in document generation to keep outputs reproducible.
