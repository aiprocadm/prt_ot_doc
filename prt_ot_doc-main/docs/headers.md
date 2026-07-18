# Headers service (NEXT-19)

## Tokens
- `{{company.name}}`, `{{site.name}}`, `{{doc.title}}` and other dotted json paths.
- `{PAGE}` and `{NUMPAGES}` are mapped to Word fields in header/footer XML.

## Notes
- Container layout uses a stable `1x1` table (`w:tbl`).
- Unknown placeholders are collected into `unresolved_placeholders` (strict, non-fatal).
- Watermark MVP injects `WATERMARK:<text>` in header content.

## API
- `POST /v1/layout-presets`
- `GET /v1/layout-presets`
- `GET /v1/layout-presets/{id}`
- `PATCH /v1/layout-presets/{id}`
- `DELETE /v1/layout-presets/{id}`
- `POST /v1/documents/{document_version_id}/apply-headers`
