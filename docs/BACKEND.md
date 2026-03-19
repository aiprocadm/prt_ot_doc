# Backend

## Entrypoints
- ASGI: `backend/app/main.py`
- Factory: `backend/app/api/app.py`
- CLI: `backend/app/cli/main.py`
- Worker: `backend/app/worker.py`

## Canonical modules for document core
- `backend/app/modules/branding/` — effective branding profile, inheritance, preview and reproducibility metadata.
- `backend/app/modules/headers/` — persisted header/footer presets and DOCX section injection.
- `backend/app/modules/templates/` — template linting and preview.
- `backend/app/modules/replace/` — replacement stage.
- `backend/app/modules/pdf/` — PDF-related endpoints/services.
- `backend/app/modules/pipelines/` — orchestration.

## Backend hardening in this wave
- Fixed site-scope preferred preset persistence in branding API.
- Added resolved watermark to branding preview response.
- Preview reproducibility now includes active preset and watermark details.
- Regression tests cover company/site inheritance and header engine invariants.

## Data model touchpoints
- `Company.branding_payload`
- `Company.preferred_header_preset_code`
- `Site.branding_payload`
- `HeaderFooterPreset.*`
