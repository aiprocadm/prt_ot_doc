# Backend

## Entrypoints
- ASGI: `backend/app/main.py`
- Factory: `backend/app/api/app.py`
- CLI: `backend/app/cli/main.py`
- Worker: `backend/app/worker.py`

## Document-related modules
- Branding: `backend/app/modules/branding/`
- Header/footer presets: `backend/app/modules/headers/`
- Replace: `backend/app/modules/replace/`
- PDF: `backend/app/modules/pdf/`
- Pipelines: `backend/app/modules/pipelines/`

## Data model additions
This wave introduces branding persistence on:
- `Company.branding_payload`
- `Company.preferred_header_preset_code`
- `Site.branding_payload`
