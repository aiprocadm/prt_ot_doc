# CHANGELOG

## 2026-05-05 (Session 17 — Phase 3.1d: DocumentReadinessRule)
- **`backend/app/modules/data_quality/rules.py`** — добавлено правило **`DocumentReadinessRule`** (`document_readiness`): DRAFT-документы старше **7** суток без `template_version_id` (MEDIUM, `missing_field`); DRAFT с привязанной `TemplateVersion`, у которой в `required_fields_schema` задан массив **`required`**, — проверка последней ревизии `DocumentVersion.data_json` на пустые обязательные поля (учёт вложенных корней `values` / `payload` / `fields` / `data`). Движок: **10 правил**.
- **`tests/test_data_quality.py`** — класс `TestDocumentReadinessRule` (4 кейса), `expected_rules` в `TestDataQualityService` дополнен `document_readiness`.
- **Frontend:** без изменений (`document` + `missing_field` уже в `WorkspaceDataQualityPage.tsx`).
- **Validation:** локальный прогон `pytest tests/test_data_quality.py` в этой сессии не выполнен (Python runtime недоступен в agent shell); ожидается CI / локально: `python -m pytest tests/test_data_quality.py -p no:schemathesis`.

## 2026-05-04 (Session 16 — Phase 3.1c: восстановление OrphanedAssignmentsRule + CompanyRequisitesRule + починка регрессии в test_data_quality.py)
- **`backend/app/modules/data_quality/rules.py`** — восстановлены два правила Data Quality движка, удалённые во время merge `17e3c61` ⇒ движок снова содержит **9 правил** (из 7 обратно до 9): `OrphanedAssignmentsRule` (ACTIVE-сотрудники с `position_id`/`workplace_id` на soft-deleted записи; HIGH/MEDIUM) и `CompanyRequisitesRule` (компании без INN — HIGH; без OGRN/legal_address — LOW). Оба зарегистрированы в `DataQualityRuleEngine.rules`.
- **`tests/test_data_quality.py`** — починена регрессия collection-error: импорт `OrphanedAssignmentsRule` оставался после отката, но самого класса в коде не было. Добавлен импорт `CompanyRequisitesRule`, восстановлены классы `TestOrphanedAssignmentsRule` (3 кейса) и `TestCompanyRequisitesRule` (3 кейса), `expected_rules` в `TestDataQualityService` расширен до 9 правил.
- **Заодно починены два пред-существующих бага в `TestDocumentPersonCompanyMismatchRule`**: тесты создавали несколько `Company`/`User` с одинаковыми дефолтными `name`/`email`, что нарушало `uq_company_tenant_name` и `uq_user_email_tenant`. Передаются явные уникальные значения.
- **Frontend не менялся**: `WorkspaceDataQualityPage.tsx` уже корректно отрисовывает новые правила (типы `missing_field`/`broken_relationship` и сущности `person`/`company` поддерживаются `ISSUE_TYPE_LABELS`/`ENTITY_TYPE_LABELS`/`ENTITY_DRILL_DOWN`).
- **Validation:** `python3.12 -m pytest tests/test_data_quality.py -p no:schemathesis` → **20 passed (0:01:21)** в чистом окружении после установки `requirements.txt` + `requirements-dev.txt`.

## 2026-05-04 (Session 15 — Phase 3.1b: Frontend Data Quality Dashboard)
- **`frontend/src/pages/workspace/WorkspaceDataQualityPage.tsx`** — заменена страница-заглушка на реальный дашборд качества данных поверх `/api/v1/data-quality/report`: severity-карточки (полнота / critical / high / medium / low), срезы по типу проблемы и сущности (с интерактивной фильтрацией), топ-20 нарушений с фильтром по уровню риска, drill-down на реестры (`/persons`, `/companies`, `/documents`, `/risk`, `/medical`, `/training`, `/contractors`, `/ppe`, `/incidents`), таблица покрытия rule-классами с временем выполнения.
- **`frontend/src/api/dataQuality.ts`** — добавлен API-клиент `dataQualityApi.getReport()` поверх `apiClient`.
- **`frontend/src/types/dto/dataQuality.ts`** — DTO-типы (`DataQualityReportDto`, `DataQualityIssueDto`, `DataQualityCheckResultDto`, `DataQualityIssueSeverity`, `DataQualityIssueType`), зеркальные backend-схемам `app.modules.data_quality.schemas`.
- **`frontend/src/__tests__/WorkspaceDataQualityPage.test.tsx`** — Vitest-юнит-тесты (5 кейсов): рендер карточек/срезов из API, фильтрация по severity, drill-down link, empty state, error state + retry.
- **Backend не менялся**: используется уже существующий эндпоинт `/api/v1/data-quality/report` (бэкенд Phase 3.1 — 7 правил Data Quality).

## 2026-05-04 (Session 14 — TZ doc-set consolidation)
- **`docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`** — починена иерархия заголовков (103 нарушения: подразделы `## N.M` → `### N.M`), внутренние подзаголовки h3→h4, добавлено полное оглавление, преамбула явно отсылает к канону.
- **`docs/spec/mapping.md`** — переписан полностью под текущую структуру `backend/app/modules/*` + `frontend/src/{features,pages}/*`; устаревшие пути (`backend/app/core/security.py` как RBAC, несуществующие домены) удалены; добавлены теги MVP/vNext.
- **`docs/MODULES.md`** — переписан как актуальная инвентаризация всех 41 модуля + 13 легаси-доменов с привязкой к канону/vNext §X.
- **`docs/ARCHITECTURE.md`** — переписан как короткий навигатор по канону + правила доработки vNext §36.
- **`docs/spec/PLATFORM_DESIGN.md`** — перестал называться «Source of Truth»; теперь рабочее описание MVP-архитектуры со ссылкой на канон.
- **`docs/spec/TZ_FULL_UNIFIED.md`** — Прил. 4 заменено на полную таблицу `bounded context → реальный модуль/роут → статус`; уточнены «Канонические пути» в шапке.
- **`docs/audit/TZ_COVERAGE_MATRIX.md`** — устранены дубли REQ-ID (`TZ-2.3-MVP-01`, `TZ-2.5-MVP-01`); тесты объединены; матрица 46 строк, валидация проходит.
- **`scripts/audit/check_tz_coverage_matrix.py`** — добавлена проверка уникальности REQ-ID.
- **`docs/facts.md`** — баннер DEPRECATED (снимок ранней волны), включён в Wave 4 cleanup.
- **`KNOWN_LIMITATIONS.md`** — обновлена дата и добавлена ссылка на канон.
- **Код не менялся** (кроме валидатора скрипта).

## 2026-05-04 (Session 13 — TZ canonicalization)
- **TZ canonicalization:** `docs/spec/TZ_FULL_UNIFIED.md` назначен **каноническим и единственным источником истины** для фразы «продолжай по ТЗ». Внутри добавлены разделы A (MVP-объём), B (полный объём vNext с тегами `[v1.1]/[v1.2]/[v2.0]`), C (где смотреть статус), D (фазы реализации), E (правила доработки — разд. 36 vNext), F (vNext §35), G (карта канонических документов и запрет на дубли), H (шаблон финального отчёта в PR), приложения 1–4. Раздел B содержит сжатые формулировки + ссылки на `PLATFORM_VNEXT_UPGRADE_SPEC.md §1..§34`, чтобы не плодить дубли.
- **Документация-навигация:** `AGENTS.md`, `docs/AI_AGENT_WORKFLOW.md`, `docs/spec/README.md`, `docs/spec/TZ_OVERVIEW.md`, `README.md`, `.cursor/rules/tz-spec-priority.mdc`, `.cursor/rules/ai-agent-workflow.mdc` — все согласованно ведут в `TZ_FULL_UNIFIED.md` как первую и единственную точку входа.
- **Deprecated:** `docs/NEXT_FEATURES.md` (полностью покрыт разделом B канона), `docs/spec/TZ.md` (история v1.0), `docs/SPEC_TRACEABILITY_MATRIX.md` (перекрыт `docs/audit/TZ_COVERAGE_MATRIX.md`), `docs/spec_compliance_report.md`, `docs/p1_compliance_report.md` — баннер deprecated добавлен; кандидаты на удаление в Wave 4 (см. `docs/CLEANUP_CANDIDATES.md`).
- **AI handoff:** `AI_IMPLEMENTATION_REPORT.md` — Session 13 (Claude Opus 4.7) с описанием канонизации и «Следующий точный шаг» (Phase 0 baseline re-verification).
- **Код не менялся** — это документация-канонизация.

## 2026-04-29
- **Status report:** `AI_IMPLEMENTATION_REPORT.md` §27 — baseline verification ✅, release NOT READY (RB-001..005 pending, RB-006 ✓ done). Три опции для next action: Release focus (RB-001/004), Feature focus (TZ_FULL P0–P1), или Developer productivity (full pytest + cleanup warnings). Репо стабилен, dokumentacija актуальна, нет новых дефектов.
- **Documentation:** `docs/stabilization/PYTEST_FULL_RUN.md` — пошаговая инструкция для полного `pytest` прогона на 287+ тестов (Developer productivity опция). Включает troubleshooting, expected results, и связанные команды.
- **CHANGELOG:** обновлена запись за 2026-04-29 с новым документом и инструкциями для Опции C.

## 2026-04-28
- **Agent workflow:** `docs/AI_AGENT_WORKFLOW.md` — объединён с расширенным брифом (обязательный порядок README→ТЗ/ссылки→`AI_IMPLEMENTATION_REPORT`→код, мусор, проверки, формат краткого ответа, условия обновления README). Обновлён `.cursor/rules/ai-agent-workflow.mdc`. В `AI_IMPLEMENTATION_REPORT.md` — кандидаты на архивацию, §12–13.
- **Repo hygiene:** из индекса удалены случайные gitlink-записи `Создание платформы по ОТ/{admiring-hellman-bd8c51,youthful-poitras-cc7163}` (без `.gitmodules`); в `.gitignore` добавлена вложенная папка-дубликат проекта, в духе политики «no nested copy» из README.

## 2026-04-27
- **Docs:** `docs/TESTING.md` — восстановлен полноценный гайд (без самоссылки); выравнено с `docs/TEST_BASELINE.md` / CI.
- **Frontend:** `frontend/src/features/tasks/TaskTable.tsx` — добавлен импорт `usePolling` из `@/hooks/usePolling` (устранён падение `tsc --noEmit`).
- **Docs:** `docs/README.md` — ссылка на `AI_IMPLEMENTATION_REPORT.md` для передачи контекста между волнами/агентами.
- **Tests:** `tests/conftest.py` — исправлен импорт `click.core.UNSET` (только внутри `try/except`, иначе pytest не стартовал на Click без символа `UNSET`). Добавлена нормализация пустого `SECRET_KEY` / обязательных S3-полей для `bootstrap("api")` в тестовой среде.
- **Docs:** `docs/TESTING.md` — восстановлен канонический гайд (было самоссылка); `docs/testing.md` — краткий указатель на `TESTING.md`. Добавлен `AI_IMPLEMENTATION_REPORT.md` с итогом волны.

## 2026-04-05
- Закрыт пробел изоляции аренды на `POST /api/v1/templates/{template_id}/versions` (legacy multipart): без проверки `template.tenant_id` можно было привязать версию к чужому шаблону при валидном JWT другой аренды на SQLite/единой схеме. Добавлена та же семантика «не найдено», что у catalog/upload (`_tenant_scope` + `deleted_at`).
- В `preview_template_version` после повторного `session.get(Template)` добавлена явная проверка аренды и soft-delete, чтобы не обращаться к полям при несогласованных данных.
- В `POST .../pipelines/runs/{run_id}/steps/{step_run_id}:retry` добавлена проверка `DocumentJobStep.tenant_id` против текущего тенанта (защита от подбора id шага).
- Восстановлен реэкспорт `roles_from_jwt_claims` из пакета `app.core.security` (используется `TenantMiddleware` и unit-тесты); без него импорт приложения падал.
- Регрессия: `tests/integration/test_cross_tenant_resource_matrix.py::test_legacy_post_template_version_returns_404_for_other_tenant_template`.
- Инвентаризация tenant row `session.get`: добавлен `docs/stabilization/TENANT_ROW_GET_INVENTORY.md`; чеклист ссылается на него вместо сырого бэклога.
- EDO workflow: проверка аренды для `ApprovalRoute` при передаче `route_id`, для `DocumentVersion` при старте approval и создании подписи, для route при шаге approve.
- Пакеты: сверка `TemplateVersion.tenant_id` с пакетом в `packs.run`; в `modules/packs/api.py` — при валидации preset.
- `document_insights`: не подмешивать шаблон/версию/NPA чужой аренды при fallback `get` по PK.
- Workflow/sign: дополнительные проверки `tenant_id` для definition/instance/version и для `ApprovalInstance` в модуле подписи.
- PWA offline sync: `OfflineSyncService.apply_batch` отклоняет батч, если `BriefingEntry` из другой аренды, чем `OfflineSyncBatch`; `get_status` принимает `tenant_id` и фильтрует в SQL; тест `test_offline_sync_fails_when_briefing_entry_other_tenant`.
- Approval signing v1: после валидного `ApprovalTask` проверяются `ApprovalProcess` и `ApprovalRoute` на совпадение с текущим тенантом перед решением по задаче.
- Training: при успешной сдаче теста срок действия (`expires_at`) из `TrainingProgram.validity_months` выставляется только если программа в той же аренде, что и enrollment.
- Pipeline: `validate_template_step_handler` ограничивает выбор `TemplateVersion` по `tenant_id` и отбрасывает `current_version_id`, указывающий на чужую аренду или другой шаблон; `PackGenerationPipeline.plan_documents` проверяет совпадение аренды версии с пакетом.
- External registry dispatch: не обновлять сертификат/протокол, если `job.tenant_id` не совпадает с арендой сущности.
- Briefings: `valid_until` из шаблона только при совпадении `BriefingTemplate.tenant_id` с `BriefingEntry.tenant_id`; тесты `test_registry_dispatch_does_not_update_certificate_other_tenant`, `test_briefing_complete_skips_validity_when_template_other_tenant`.
- Approvals module service: сравнение аренды через `str()` для маршрута и инстанса; шаги инстанса в `decide` отфильтрованы по `tenant_id`.
- Packs: `load_source_rows` принимает `tenant_id` и отклоняет чужой `File`; вызовы из `packs/api` передают текущий тенант; `replace/repo.get_replace_run` — согласованное сравнение `tenant_id`.

## 2026-03-29
- Hardened tenant identity handling across document-core so `tenant.id` is again the canonical persistence identifier for `Template`, `TemplateVersion`, `DocumentPack`, `DocumentPackItem`, and `PipelineRun`, while `tenant.slug` remains routing-only and `tenant_schema` remains schema-only.
- Updated session/dependency contract to hydrate `session.info` with `tenant_id`, `tenant_slug`, and `tenant_schema`; legacy `session.info["tenant"]` now survives only as a backward-compatible slug alias.
- Fixed document pipeline and package/job entrypoints that were passing `tenant_slug` into `tenant_id`, including `backend/app/services/pipeline.py`, `backend/app/services/tasks.py`, `backend/app/services/package_pipeline.py`, `backend/app/domains/packs/seeder.py`, `backend/app/repository.py`, `backend/app/tasks.py`, and `backend/app/api/v1/router.py`.
- Added regression coverage for tenant session contract, pipeline tenant consistency, tenant-scoped package persistence, and dashboard quick-action routing.
- Wired dashboard quick actions to the real document wizard and pack wizard flows.

## 2026-03-26
- Stabilized tenancy session propagation for FK-backed tenant models by separating `tenant_id`, `tenant_slug`, and `tenant_schema` in session context and preventing slug autofill into UUID-backed `tenant_id` fields.
- Fixed demo bootstrap so FK-backed entities use the real tenant UUID instead of tenant slug values.
- Formalized stateless logout with `POST /auth/logout -> 204 No Content` and documented that clients must clear local tokens because backend-side refresh-token revocation is not yet implemented.
- Removed unreachable quota code from `backend/app/api/v1/router.py` and kept `assert_quota(...)` as the single active generation quota path.
- Hardened CORS configuration so credentialed requests cannot start with wildcard origins; added settings and app-factory regression coverage for this.
- Realigned `docs/openapi.yaml` with the runtime auth contract and added contract tests for `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/logout`, `/api/v1/auth/me`, and `/api/v1/auth/me/permissions`.
- Removed critical runtime route collisions on canonical URLs for prescriptions, files, training certificates, approvals, and EDO list endpoints by moving overlapping legacy aliases to explicit namespaced/versioned paths; added a regression test for duplicate path+method registration on these critical routes.
- Fixed runtime schema bootstrap for tenants with explicit `schema_name`: session bootstrap, dependency resolution, dev bootstrap, demo bootstrap, and tenant bootstrap service now create/use the recorded schema instead of recomputing `tenant_<slug>`.
- Disabled implicit schema auto-create in ordinary runtime session paths by default behind `RUNTIME_SCHEMA_BOOTSTRAP`; explicit bootstrap routines remain responsible for intentional schema creation in dev/test setup flows.

## 2026-03-21
- Added canonical docs: `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`, `docs/DEMO_ACCESS.md`, `docs/OWNER_ADMIN_ACCESS.md`, `docs/USER_ACCESS_AND_ROLES.md`.
- Hardened template catalog contract with category/status/scope fields.
- Fixed template version upload so the uploaded version becomes `current_version_id` consistently.
- Normalized generation-time template resolution to support both `code` and legacy `name` lookups.
- Removed duplicate/broken template schema and router fragments that were causing invalid backend/frontend template contracts.
- Restored a coherent templates UI contract by fixing DTOs, form schema and the template form dialog around `scope.type`.
- Added regression tests for template scope metadata and current-version linking.

### Added
- Introduced a dedicated notifications application module at `backend/app/modules/notifications/` with explicit schemas and service boundaries.
- Added canonical docs: `docs/TRAINING_AND_LMS.md`, `docs/RISK_ENGINE.md`, `docs/ACCEPTANCE_SCENARIOS.md`, and this changelog.
- Added `CHANGED_MODULES_AND_DECISIONS.md` to document the wave-level architectural decisions.

### Changed
- Slimmed `backend/app/api/routes/notifications.py` so the router now delegates business logic to the notification application service instead of querying models directly.
- Normalized notification enum validation so invalid `status`/`priority`/`channel`/`type` values fail with structured 422 responses instead of leaking `ValueError` behavior.
- Hardened notification query validation so malformed `cursor` values and unsupported calendar `source` values now return the canonical structured 422 contract instead of generic failures or silent empty responses.
- Expanded notification API acceptance coverage in `tests/api/test_notifications_calendar_api.py`.
- Reworked unread counting to use aggregate SQL count semantics instead of materializing all unread notifications in memory.
- Updated acceptance, gap, release-readiness, and architecture docs to reflect the real state of notifications/training/risk hardening.
- enhanced template DTOs with scope/type/current-version/version-history;
- added template version patch endpoint for lifecycle updates;
- updated templates UI to show scope/type and use backend-aligned DTOs;
- added canonical docs for template upload/rendering, demo access, owner/admin access and user access issuance.
