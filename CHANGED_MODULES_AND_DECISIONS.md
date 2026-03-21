# CHANGED_MODULES_AND_DECISIONS

## 2026-03-21 wave

### Template contract normalization
**Changed modules/files**
- `backend/app/modules/templates/schemas.py`
- `backend/app/api/v1/router.py`
- `backend/app/schemas/common.py`
- `frontend/src/types/dto/templates.ts`
- `frontend/src/types/forms/templates.ts`
- `frontend/src/features/templates/TemplateFormDialog.tsx`
- `frontend/src/features/templates/TemplateDetails.tsx`

**Decision**
- Keep storage backward-compatible by persisting scope/category in `metadata_json`, while exposing a normalized API/UI contract now.

**Why**
- Repo already had template entities and working flows; big-bang schema rewrite would be risky.
- The next wave needs a clear canonical contract in code and docs.

### Generation lookup hardening
**Changed files**
- `backend/app/api/routes/documents.py`

**Decision**
- Resolve templates by `code` or legacy `name`.

**Why**
- Existing code used both conventions in different places, creating fragile production behavior.

### Access/bootstrap documentation
**Changed docs**
- `README.md`
- `docs/DOCUMENT_CORE.md`
- `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`
- `docs/DEMO_ACCESS.md`
- `docs/OWNER_ADMIN_ACCESS.md`
- `docs/USER_ACCESS_AND_ROLES.md`
- root release/gap/acceptance docs.
