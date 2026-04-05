# Инвентаризация `session.get` / `self.session.get` (tenant row guard)

**Снимок:** 2026-04-05  
**Область:** `backend/app/api/`, `backend/app/modules/`, `backend/app/services/`  
**Основание:** [TENANT_ROW_GET_CHECKLIST.md](./TENANT_ROW_GET_CHECKLIST.md)

## Зачем этот документ

Фиксирует, где ORM делает загрузку по PK без `WHERE tenant_id`, и какой механизм изоляции применён. При добавлении новых маршрутов или сервисов — обновить соответствующий раздел и прогнать команду воспроизведения ниже.

### Воспроизведение списка вызовов

```bash
rg "await session\.get\(|await self\.session\.get\(" backend/app/api backend/app/modules backend/app/services
```

## Легенда статусов

| Код | Значение |
|-----|----------|
| **A** | Явно `enforce_row_belongs_to_tenant` или `assert_tenant_row_matches_session` |
| **B** | Ручная проверка `row.tenant_id` / `str(row.tenant_id) == …` / `_tenant_scope` / helper `_*_for_tenant` / `select … where tenant_id` сразу после `get` или в том же блоке |
| **C** | ID не с внешнего «сырого» path (внутренний FK по уже проверенной строке); риск cross-tenant по классу ниже, если цепочка FK целостна |
| **D** | Сервис с параметром `tenant_id`; вызывающий код обязан открывать tenant-сессию; внутри добавлены проверки там, где загрузка шла без фильтра |
| **R** | Остаточный риск / фон / очередь без явной привязки batch→tenant в этом участке — вынести в отдельную задачу при изменении модуля |

---

## Сводка по верхнему уровню

| Зона | Вызовов `get` (оценка) | Доминирующий паттерн |
|------|-------------------------|----------------------|
| `app/api/routes/*.py` | ~90+ | **B** на большинстве CRUD; **A** на jobs/files/webhooks/outbox/documents |
| `app/api/v1/router.py` | 14 | **B** (`_tenant_scope`, `deleted_at`) |
| `app/modules/*` | ~45 | **B** / **D** (`WorkflowService`, `PipelineEngine`, search) |
| `app/services/*` | ~15 | **A** в `pipelines_orchestrator`; остальное **D**/контекст вызывающего |

---

## `app/api/routes` — файл за файлом

| Файл | Статус | Комментарий |
|------|--------|-------------|
| `jobs.py` | **A** | `enforce_row_belongs_to_tenant` + assert на стриме |
| `files.py` | **A** | `enforce_row_belongs_to_tenant` для `StoredFile` |
| `webhooks.py` | **A** | `enforce_row` на endpoint/delivery/outbox |
| `outbox_admin.py` | **A** | `enforce_row` |
| `documents.py` | **A** | `assert_tenant_row_matches_session` в `_ensure_company` / `_ensure_person` |
| `v1/router.py` | см. отдельно | Шаблоны: **B** |
| `packs.py` | **B** | После `get(TemplateVersion)` добавлена сверка `version.tenant_id` с `pack.tenant_id` (защита SQLite) |
| `obligations.py` | **B** | `task.tenant_id != tenant.id` |
| `client_portal.py` | **B** | `_get_run_for_tenant`, preset patch |
| `api_tokens.py` | **B** | `token.tenant_id` |
| `audit.py` | **B** | `AuditLog` / `AuditExportJob` |
| `briefings.py` | **B** | `BriefingTemplate` / `BriefingEntry` |
| `training_next.py` | **B** | Последовательные проверки на программах/модулях/тестах/… |
| `risk.py` | **B** | `_get_tenant_entity`; `Site` после `ensure_site_belongs_to_tenant` |
| `tenants.py` | **B** | `get(Tenant)` + сверка с текущим контекстом сессии |
| `risk_enterprise.py` | **B** | Проверки `tenant_id` после get методологий/карт |
| `public_api.py` | **B** | `ApiKey`, `MarketplaceCatalogItem` |
| `approval_orchestration.py` | **B** | В т.ч. `_get_document_for_tenant` / `_get_pack_for_tenant` |
| `approval_signing_v1.py` | **B** | После проверенного task явная сверка tenant для `ApprovalProcess` и `ApprovalRoute` в `POST .../tasks/{id}:decide` |
| `edo_workflow.py` | **B** | Усилено 2026-04-05: `ApprovalRoute` по `route_id` только при совпадении tenant; `DocumentVersion` по телу запроса с проверкой tenant; route при approve |

---

## `app/api/v1/router.py` (шаблоны)

Все `get(Template)` / `get(TemplateVersion)` с ID из path/form: **B** — сравнение с `_tenant_scope(tenant)` и `deleted_at`, либо согласование `template_id`/`version_id` в одном запросе.

---

## `app/modules`

| Файл | Статус | Комментарий |
|------|--------|-------------|
| `pipelines/api.py` | **B** | Сверка `DocumentJob`/`tenant`; шаг retry — `DocumentJobStep.tenant_id` |
| `pipelines/orchestrator.py` | **A** | `assert_tenant_row_matches_session` |
| `files/api.py` | **A** | `enforce_row` |
| `files/service.py` | **D** | Методы с `tenant_id` аргумента; проверки у записи при get |
| `search/service.py` | **B** | `SearchSavedQuery`: `tenant_id` + `user_id` |
| `workflow/service.py` | **B** | Усилено 2026-04-05: `WorkflowDefinition` при `start_instance`, `WorkflowInstance` при complete task, версия в `_advance` / `run_due_timers` |
| `training/services.py` | **B** | `submit_attempt`: `TrainingProgram` по PK только если `program.tenant_id == enrollment.tenant_id` перед расчётом `expires_at` |
| `sign/service.py` | **B** | Усилено: `ApprovalInstance.tenant_id` при create signature request |
| `replace/api.py` | **B** | Явные проверки tenant на картах и версиях документа |
| `replace/repo.py` | **D** | Зависит от вызывающего контекста |
| `pwa_sync/services.py` | **B** | `apply_batch`: при `briefing_entry` сверка `entry.tenant_id` с `batch.tenant_id` → иначе `failed` + `tenant_scope_mismatch`; `get_status(..., tenant_id=)` для HTTP — фильтр в SQL |
| `pdf/api.py` | **B** | `File`, `PdfConversionRun` |
| `packs/api.py` | **B** | `PackRun`; validate preset — сверка `TemplateVersion.tenant_id` с preset (2026-04-05) |
| `packs/service.py` | **D** | Проверять при изменении пакетных сценариев |
| `headers/api.py` | **B** | Preset + `DocumentVersion` |
| `external_registry/services.py` | **D** | Загрузка сущностей по `job.entity_id` в контексте job/tenant |
| `briefings/services.py` | **C/D** | Шаблон по `entry` — FK из entry |
| `approvals/service.py` | **D** | Сервис с `tenant_id` в конструкторе — проверить вызовы при рефакторинге |

---

## `app/services`

| Файл | Статус | Комментарий |
|------|--------|-------------|
| `pipelines_orchestrator.py` | **A** | `assert_tenant_row_matches_session` на job/step/profile |
| `document_insights.py` | **D** | Усилено 2026-04-05: `Template`/`TemplateVersion`/`NPA` только при совпадении `tenant_id` с аргументом функции |
| `pipeline_step_handlers.py` | **B** | Выбор версии по номеру с `TemplateVersion.tenant_id == job.tenant_id`; при `get(current_version_id)` — отбрасывание строк с чужим tenant или чужим `template_id` |
| `package_pipeline.py` | **B** | После резолва версии — `version.tenant_id` vs `pack.tenant_id` |
| `billing.py` | **N/A** | `BillingPlan` без tenant на строке подписки — план глобальный по продукту |
| `obligations.py` | **D** | Загрузка `Prescription` по `task.entity_id` в worker-контексте |

---

## Изменения кода (волна инвентаризации, 2026-04-05)

- `edo_workflow.py`: tenant для маршрута по `route_id`, для `DocumentVersion` в старте approval и в `create_signature`, tenant для route при approve.
- `packs.py` (routes): выравнивание tenant версии шаблона с пакетом.
- `modules/packs/api.py`: validate preset — tenant версии vs preset.
- `document_insights.py`: отсечение чужих template/version/NPA при `get` по PK.
- `modules/sign/service.py`: tenant для `ApprovalInstance` в signature flow.
- `modules/workflow/service.py`: tenant для definition/instance/version в критичных ветках.
- `modules/pwa_sync/services.py` + `api/routes/pwa_sync.py`: сверка entry↔batch, статус батча по SQL с `tenant_id`.
- `approval_signing_v1.py`: tenant для process/route в decide task.
- `modules/training/services.py`: tenant при загрузке `TrainingProgram` для `expires_at` после попытки теста.
- `services/pipeline_step_handlers.py`: фильтр `tenant_id` при выборе версии по номеру; защита `get(current_version_id)` от чужой аренды / чужого шаблона.
- `services/package_pipeline.py`: сверка `TemplateVersion.tenant_id` с `DocumentPack.tenant_id` в `plan_documents`.

Подробнее — [CHANGELOG.md](../../CHANGELOG.md).

---

## Этап 2 (рекомендуемый бэклог)

1. **Единообразие:** по желанию заменить повторяющиеся **B** на `enforce_row_belongs_to_tenant` в однотипных CRUD (без смены HTTP-кодов).
2. **Повторный снимок:** после крупных PR в перечисленных каталогах — обновить таблицы и дату в шапке.

---

## Связанные документы

- [TENANT_ROW_GET_CHECKLIST.md](./TENANT_ROW_GET_CHECKLIST.md) — правило и закрытые hot-path.
- [ARCHITECTURE_DECISIONS_STABILIZATION.md](./ARCHITECTURE_DECISIONS_STABILIZATION.md) — решения по guard в фоне.
