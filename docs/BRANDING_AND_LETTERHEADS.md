# Branding and letterheads

## Supported branding profile fields
- Legal and short name.
- INN / KPP / OGRN.
- Legal and actual address.
- Website / email / phones.
- Footer requisites and service notes.
- Branch label.
- Preferred letterhead preset.
- Watermark text + enable flag.
- Image refs for logo / stamp / signature.
- Palette, metadata and signatories.

## Inheritance model
- Tenant branding acts as global default.
- Company branding defines legal entity defaults.
- Site branding overrides company details for a branch/object.

## API
- `GET /api/v1/branding/profile?company_id=...&site_id=...`
- `PATCH /api/v1/branding/profile/{company_id}`
- `POST /api/v1/branding/preview`
- `GET /api/v1/layout-presets`
- `POST /api/v1/layout-presets`
- `PATCH /api/v1/layout-presets/{preset_id}`
- `POST /api/v1/documents/{document_version_id}/apply-headers`

## UI
- `/documents/branding` — main operator screen.
- `/admin/layout-presets` — preset maintenance.

## Operational scenario
1. Select organization.
2. Optionally switch to branch/site scope.
3. Maintain requisites and image references.
4. Choose preferred letterhead preset.
5. Run preview and inspect resolved watermark + reproducibility passport.
6. Use the same preset code when generating the final document.
