# CHANGELOG

## 2026-04-27
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
