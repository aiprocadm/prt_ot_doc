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
