# TEMPLATE_UPLOAD_AND_RENDERING

## Audit findings (2026-03-21)
- Template lifecycle already existed in `backend/app/api/v1/router.py`, but was split between `POST /templates/catalog`, legacy `POST /templates`, and version upload endpoints, which created contract drift.
- Template versions, linter, preview, DOCX render and passport generation were already present in `backend/app/modules/templates/*`, `backend/app/modules/replace/*`, `backend/app/modules/pdf/*`, and `backend/app/api/routes/documents.py`.
- Upload/version flows lacked a canonical representation of template scope (tenant / organization / branch-site) in the main DTO returned to the frontend.
- Frontend template DTOs did not match backend contracts: the UI expected `current_version`, `versions`, `category`, and `tags`, while the backend primarily returned `status`, `current_version_id`, `metadata_json`, and version endpoints separately.
- Custom-template preparation for a concrete organization/branch was partially implemented through company/site-aware document generation, but the repo lacked a single canonical doc that tied together template scope, upload, lint, preview, render, headers/footers, replace and PDF.

## Canonical backend paths
- Template metadata + lifecycle routes: `backend/app/api/v1/router.py`
- Template rendering/linting/passport helpers: `backend/app/modules/templates/`
- Replace engine: `backend/app/modules/replace/`
- PDF conversion: `backend/app/modules/pdf/`
- Document generation orchestration: `backend/app/api/routes/documents.py`
- Document entities and snapshots: `backend/app/models/document.py`

## Supported flow
1. Create template catalog card with code, name, description, type and scope.
2. Upload DOCX as a template version.
3. Run lint to inspect placeholders / control blocks.
4. Render preview with sample JSON.
5. Generate tenant/company/site-specific document through document generation flow.
6. Continue into header/footer, replace, PDF, approval/sign/archive flows.

## Scope model
Template scope is stored in `Template.metadata_json.scope` and returned in API DTOs.

Supported `scope.type` values:
- `global` / `system`
- `tenant`
- `organization` / `legal_entity`
- `site` (used as branch/facility scope in code)

Recommended override order:
1. `site`
2. `organization`
3. `tenant`
4. `global/system`

## API endpoints
- `GET /api/v1/templates`
- `POST /api/v1/templates/catalog`
- `GET /api/v1/templates/{template_id}`
- `PATCH /api/v1/templates/{template_id}`
- `POST /api/v1/templates/{template_id}/versions:upload`
- `GET /api/v1/templates/{template_id}/versions`
- `GET /api/v1/templates/{template_id}/versions/{version_id}`
- `PATCH /api/v1/templates/{template_id}/versions/{version_id}`
- `POST /api/v1/templates/{template_id}/versions/{version_id}:lint`
- `POST /api/v1/templates/{template_id}/versions/{version_id}:preview`
- `POST /api/v1/templates/render-preview`
- `POST /api/v1/documents/generate`

## Example: create tenant-scoped template card
```json
{
  "code": "order-safety-briefing",
  "name": "Приказ о назначении ответственного",
  "description": "Кастомный шаблон клиента",
  "template_type": "order",
  "status": "draft",
  "scope": {
    "type": "tenant"
  }
}
```

## Example: create branch/site-scoped template card
```json
{
  "code": "site-work-permit",
  "name": "Наряд-допуск для площадки",
  "template_type": "permit",
  "scope": {
    "type": "site",
    "company_id": "<company-id>",
    "site_id": "<site-id>"
  }
}
```

## Version upload form fields
Multipart form supports:
- `file`
- `document_type`
- `applicability_rules` (JSON object)
- `output_types` (JSON array)
- `profile` (JSON object)
- `status_value`

## Rendering capabilities
Current foundation supports:
- `{{ variable }}` placeholders
- conditionals / loops detected by linter
- nested control blocks recognition
- sample JSON preview render
- input hashing / correlation id / passport metadata
- output artifacts for DOCX and downstream PDF pipeline

## Org / branch preparation scenario
1. Create company in `/api/v1/companies`.
2. Create branch/site in `/api/v1/sites` if needed.
3. Create a template with `organization` or `site` scope.
4. Upload a DOCX version.
5. Run lint and preview with organization/branch payload.
6. Generate document via `/api/v1/documents/generate` using the target company and selected template version.
7. Apply brand/header-footer profile where required.
8. Convert to PDF and continue to approval / sign / archive.

## Known boundaries
- Automatic template resolution by override chain is partially represented by scope metadata and repo conventions; the operator still selects the desired template/version explicitly in the main generation flow.
- Branch is represented in the backend as `Site`; docs and UI refer to it as branch/site where relevant.
