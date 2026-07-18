# MODULES

> **Канонический ТЗ:** [`docs/spec/TZ_FULL_UNIFIED.md`](./spec/TZ_FULL_UNIFIED.md). Полный каталог модулей и bounded contexts — `vNext §28.3` в [`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./spec/PLATFORM_VNEXT_UPGRADE_SPEC.md).
>
> Назначение этого файла — **актуальная инвентаризация** backend-модулей и их frontend-/test-сопровождения. Не дублируйте сюда требования из канона.

## Backend layout

В backend сосуществуют два слоя:

- **`backend/app/modules/*`** — целевой слой (новый код, bounded contexts по vNext §28.3). Здесь идёт основное развитие.
- **`backend/app/domains/*`** — легаси-домены (постепенно поглощаются `modules/`). Не делать новых файлов здесь без явной причины; см. `docs/audit/REPOSITORY_AUDIT.md` (раздел «Legacy / compatibility paths»).

## Module inventory (`backend/app/modules/*`)

### Платформенное ядро (vNext §28, §31, §32)

| Модуль | Назначение | Канон / vNext | Frontend / тесты |
|--------|-----------|---------------|-----------------|
| `tenancy` | tenant context, schema-per-tenant, search_path | A.2.1 / vNext §32 | `frontend/src/stores/tenant.ts` / `tests/test_middleware_tenant.py` |
| `rbac_abac` | policy engine + ABAC + module-level access | A.2.2 / vNext §32 | `frontend/src/permissions/*` / `tests/test_rbac_*.py` |
| `audit` | append-only audit + field-diff | A.2.3 / vNext §32 | `frontend/src/features/audit/*` / `tests/test_audit_*.py` |
| `files` | загрузка/выдача с tenant-prefix | A.2.1 / vNext §32 | `frontend/src/features/files/*`, `frontend/src/pages/files/*` / `tests/test_files_*.py` |
| `notifications` | API уведомлений + calendar aggregation | vNext §4.4 | `frontend/src/pages/notifications/*` / `tests/api/test_notifications_calendar_api.py` |
| `health_checks` | comprehensive health (DB, Redis, MinIO, workers, integrations) | vNext §31.5, Phase 2.2 | — / `tests/test_health_comprehensive.py` |

### Документная фабрика (vNext §6)

| Модуль | Назначение | Канон / vNext | Frontend / тесты |
|--------|-----------|---------------|-----------------|
| `templates` | каталог шаблонов, `(code, version)` strict | A.2.5 / vNext §6.2 | `frontend/src/features/templates/*`, `frontend/src/pages/templates/*` / `tests/test_template_delete.py` |
| `branding` | tenant/company/site brand inheritance | vNext §6.3 | `frontend/src/pages/branding/*`, `frontend/src/api/branding.ts` / `tests/api/test_branding_api.py` |
| `headers` | header/footer engine | vNext §6.3 | `frontend/src/components/LayoutPresetEditor/*` / `tests/headers/test_engine.py` |
| `replace` | dry-run / diff / apply / rollback DOCX replace | A.2.9 / vNext §6.4 | `frontend/src/pages/documents/wizard/*` / `tests/test_replace_*.py` |
| `pdf` | LibreOffice headless pool + embedded fonts | A.2.10 / vNext §6.6 | `frontend/src/pages/documents/DocumentsPage.tsx` / `tests/pdf/test_validators.py` |
| `pipelines` | step orchestrator: template→headers→replace→pdf→… | A.2.8 / vNext §6.5 | `frontend/src/pages/PipelineRuns.tsx`, `frontend/src/pages/PipelineRunDetails.tsx`, `frontend/src/pages/PipelineBuilderPage.tsx` / `tests/test_next39_pipeline_orchestrator.py` |
| `jobs` | document jobs registry + retries/timings | A.2.8 / vNext §6.5 | — / `tests/test_next10_job_engine.py` |
| `doc_render` | render helpers поверх template engine | vNext §6.7 | — / встроенные тесты |
| `packs` | пакеты документов (выход на объект, НС, проверка, обучение) | A.3.5 / vNext §6.5 | `frontend/src/pages/packs/*`, `frontend/src/features/packs/*` / `tests/integration/test_packages_e2e.py` |
| `approval` / `approvals` | approval routes/processes (legacy + actual) | vNext §6.9 | `frontend/src/pages/approvals/*` / `backend/tests/test_next57_approval_sign_edo_services.py` |
| `sign` | подписи, КЭП/УНЭП/ПЭП заглушки | vNext §6.9 | `frontend/src/pages/signatures/*` / common tests |
| `edo` | ЭДО workflow (исходящие/входящие) | vNext §6.9 | `frontend/src/pages/edo/*` / common tests |
| `external_registry` | внешние регистры (ФРДО/ЕИСОТ ready) | vNext §7.5 | — / common tests |

### Master data + UX (vNext §4–§5)

| Модуль | Назначение | Канон / vNext |
|--------|-----------|---------------|
| `org_structure` | tenant → company → branch (RC-014) → site → department → person | vNext §5.1 |
| `data_quality` | rules engine (10 правил), DQ report API | vNext §5.4, Phase 3.1 backend done |
| `operational_dashboard` | command-center backend (alerts aggregator) | vNext §4.3, Phase 2.1 backend done |
| `calendar` | smart calendar aggregator | vNext §4.4 |
| `search` | universal search index | vNext §4.5 |
| `client_portal` | внешний кабинет клиента/подрядчика | vNext §15.1, §23.2 |
| `contractors` | contractor management + readiness | vNext §15 |

### Доменные модули (vNext §7–§20)

| Модуль | Назначение | Канон / vNext |
|--------|-----------|---------------|
| `risk` | risk engine (PxS / Fine-Kinney / hazards / measures) | A.3.1 / vNext §11 |
| `ppe` | СИЗ нормы, выдача/возврат, склад skeleton | A.3.2 / vNext §12 |
| `training` | программы / курсы / сессии / тесты / удостоверения | A.3.3 / vNext §7 |
| `briefings` | инструктажи + электронные журналы | A.3.3 / vNext §8 |
| `incidents` | инциденты, расследование, severity | A.3.4 / vNext §13 |
| `inspections` | проверки, чек-листы, акты | A.3.4 / vNext §14 |
| `inspection_prep` | пакет «подготовка к проверке» | A.3.5 / vNext §14 |
| `capa` | corrective actions / предписания workflow | vNext §14.3 |
| `compliance_deadlines` | НПА + obligation register + сроки | vNext §19 |

### Аналитика и расширения (vNext §24–§27)

| Модуль | Назначение | Канон / vNext |
|--------|-----------|---------------|
| `analytics` | агрегаты для дашбордов | vNext §24.1–§24.4 |
| `export_center` | экспорт отчётов | vNext §24.3 |
| `projections` | материализованные представления | vNext §24, §31.4 |
| `workflow` | rules + workflow engine (минимум) | vNext §25 |
| `pwa_sync` | offline sync framework для mobile | vNext §27.3–§27.4 |

## Legacy domains (`backend/app/domains/*`)

Статус после **ARCH-1** (2026-07-02, 8 срезов): все контексты, дублировавшиеся с
`modules/*`, свёрнуты в `modules/*`; их каталоги в `domains/*` — **deprecated
compat-shim'ы** (чистый реэкспорт, удаляются в POST-1 в следующем мажоре):

`audit`, `contractors`, `files`, `incidents`, `packs`, `ppe`, `replace`, `risk`, `sign`, `training`.

Не дублированные контексты (пары в `modules/` нет) — живут в `domains/*` до
отдельного решения; новых файлов не плодить, новое развитие — в `modules/*`:

`billing`, `committees`, `layout`, `medical`, `npa`, `permits`, `prescriptions`,
`signing`, `sout`, `templating`, `work_permits` + shared-kernel `domains/shared.py`
(`ContingentItemStatus` / `classify` — его миграция помечена как будущий срез в
`scripts/ci/check_context_boundaries.py`).

Границы enforced: `scripts/ci/check_context_boundaries.py` (ARCH-3) — новые
`modules↔domains` импорты падают; намеренные исключения — в его `ALLOWLIST`.

## Frontend counterparts

- `src/features/*` — feature-slices (`audit`, `companies`, `documents`, `files`, `npa`, `packs`, `persons`, `risk`, `tasks`, `templates`, `workflow`).
- `src/pages/*` — route-уровневые страницы (всего 82+, см. `docs/FRONTEND_SCREENS_INVENTORY.md`).
- `src/components/LayoutPresetEditor/*`, `src/permissions/*`, `src/router/*`.

## Verification companions

- `scripts/branded_document_smoke.py`
- `scripts/audit/check_tz_coverage_matrix.py`
- `scripts/repo_audit.py`
- `tests/api/test_branding_api.py`
- `tests/headers/test_engine.py`

## Cross-references

- Карта «спецификация → код» (с тегами MVP/vNext): [`docs/spec/mapping.md`](./spec/mapping.md).
- Полный продуктовый каталог bounded contexts: [`docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`](./spec/PLATFORM_VNEXT_UPGRADE_SPEC.md) §28.3.
- Целевая архитектура: [`docs/spec/PLATFORM_DESIGN.md`](./spec/PLATFORM_DESIGN.md).
- Статус MVP-требований: [`docs/audit/TZ_COVERAGE_MATRIX.md`](./audit/TZ_COVERAGE_MATRIX.md).
