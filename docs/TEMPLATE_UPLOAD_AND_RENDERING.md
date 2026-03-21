# TEMPLATE_UPLOAD_AND_RENDERING

## Что реально реализовано в repo

### Канонические backend-пути
- Каталог шаблонов: `POST /api/v1/templates/catalog`, `GET /api/v1/templates`, `GET/PATCH /api/v1/templates/{template_id}`.
- Загрузка версии DOCX: `POST /api/v1/templates/{template_id}/versions:upload`.
- Lint: `POST /api/v1/templates/{template_id}/versions/{version_id}:lint`.
- Preview: `POST /api/v1/templates/{template_id}/versions/{version_id}:preview`.
- Генерация документа: `POST /api/v1/documents/generate`.

### Канонические frontend-пути
- Реестр шаблонов: `/templates`.
- Карточка и инструменты версии: `frontend/src/features/templates/TemplateDetails.tsx`.
- Создание/редактирование карточки: `frontend/src/features/templates/TemplateFormDialog.tsx`.

## Audit findings document core
- Templates и template versions уже существуют и хранятся отдельно.
- Upload версии был реализован, но `current_version_id` мог не проставляться корректно до flush; в этой волне это исправлено.
- В коде были inconsistent контракты выбора шаблона: часть кода искала по `Template.name`, часть по `Template.code`; для генерации теперь поддерживаются оба поля.
- Scope шаблона существовал только косвенно через metadata; в этой волне он нормализован в API-контракте и UI, сохраняя storage через `metadata_json`.
- Lint/preview уже были, но docs не описывали их как canonical flow.
- Удаление используемой версии по-прежнему блокируется; production-safe правило — архивировать/деактивировать, а не удалять.

## Модель scope
Шаблон хранит scope в `Template.metadata_json.scope`:

```json
{
  "level": "tenant|company|site|system",
  "company_id": "optional",
  "site_id": "optional",
  "label": "human readable name",
  "applicability": "free text usage rules"
}
```

Текущая доменная модель repo использует `Company` и `Site`. Для сценария "филиал / branch" canonical mapping на текущем этапе — `Site`.

## Production-minded сценарий
1. Создать карточку шаблона через `/api/v1/templates/catalog`.
2. Задать `code`, `name`, `category`, `status`, `scope`.
3. Загрузить DOCX-версию через `versions:upload`.
4. Выполнить `:lint` для выявления placeholders / блоков / ошибок layout.
5. Выполнить `:preview` на sample JSON.
6. Запустить `/api/v1/documents/generate` с `template_code`/`template_version` и `company_id`.
7. При необходимости продолжить по pipeline: header/footer -> replace -> PDF -> approval/sign/archive.

## Поддерживаемые шаблоны и рендеринг
- DOCX рендеринг выполняется через `docxtpl` и Jinja-like syntax.
- Поддерживаются `{{ variable }}`, условные блоки и циклы на уровне `docxtpl`.
- Renderer пишет metadata о reproducibility: hashes входного контекста, template bytes и output bytes.
- Missing keys не валят preview безусловно: strict render пытается отработать первым, затем fallback переводит отсутствующие значения в пустые строки и сохраняет warnings.

## Header / footer / replace / PDF
- Header/footer hardening сосредоточен в `backend/app/modules/headers/`.
- PDF conversion сосредоточен в `backend/app/tasks.py` и `backend/app/modules/pdf/`.
- Replace dry-run/reporting остаётся в `backend/app/modules/replace/` и API `/replace/*`.
- На текущем этапе не каждый entrypoint автоматически выполняет полный chain `generate -> headers -> pdf`; для гарантированного e2e-flow используйте pipeline profile или последовательный вызов шагов.

## Org / branch-specific usage
- Для организации используйте `scope.level=company` + `company_id`.
- Для филиала/branch используйте `scope.level=site` + `company_id` + `site_id`.
- Для tenant-wide шаблона используйте `scope.level=tenant`.
- Для system foundation можно использовать `scope.level=system`, но текущий storage всё ещё tenant-aware и требует осознанного provisioning.

## Реальные ограничения
- Scope хранится в `metadata_json`, а не вынесен в отдельные индексы/таблицы; это осознанный non-breaking step текущей волны.
- Diff between versions, visual DOCX preview и automatic archive action для version lifecycle пока частично закрыты docs/UI-слоем, но не полностью автоматизированы на backend.
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
