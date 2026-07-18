# P10-07 Report-builder MVP — design spec

- **Дата:** 2026-07-10
- **Статус:** approved (brainstorming через AskUserQuestion, 6 решений + одобрение дизайна)
- **Ветка:** `feat/p10-07-report-builder-mvp` от `main@0aeb833a` (merge PR #730)
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B.23 → `PLATFORM_VNEXT_UPGRADE_SPEC.md` §24.3 (report builder). Roadmap: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` P10-07 «Остаётся: управленческие дашборды + report-builder UI».

## 1. Контекст (сверка код↔ТЗ, 2026-07-10)

Уже в `main`:

- `modules/analytics` — 11 dashboard-эндпоинтов + 6 trend-series поверх read-models (`modules/projections`).
- Export Center (`modules/export_center` + `modules/projections/models.py`): `ExportJob` (есть `file_id`, `row_count`, `status`, `error_payload`), `ExportSchedule` (cron), `KpiDefinition`, каталог 8 датасетов, CRUD API `/exports*`, `GET /exports/{id}/download-link` → `/api/v1/files/{file_id}/download`.
- **Дыра:** для `ExportJob` нет материализатора — job создаётся `queued` и висит навсегда (кнопки XLSX/PDF на `ReportsPage` мёртвые). Единственный образец рабочего экспорта — `celery/tasks/audit_export_job.py` (audit-only).
- Печатная инфраструктура: python-docx + LibreOffice pool (`modules/pdf/convert.py::convert_docx_bytes`), graceful-паттерн `PdfRendererUnavailable` (`services/medical_print.py`).
- `openpyxl==3.1.5` уже в `requirements.txt`.
- Frontend: `ReportsPage` (`/reports`), `ExportsPage` (`/exports`), `downloadBlob`-паттерн, `useAsyncResource`, право `REPORTS_VIEW`.

Нет: сущности «report definition» (конструктора), материализатора, UI-конструктора.

## 2. Решения (зафиксированы пользователем)

1. **Срез P10-07 = Report-builder MVP end-to-end** (не управленческие дашборды — они следующие).
2. **Объём конструктора:** датасет → фильтры → выбор колонок → сортировка → **группировки с агрегатами count/sum** («расчётные показатели» из ТЗ). Графики/heatmap — follow-up.
3. **Форматы экспорта: CSV + XLSX + PDF** (все три в этом срезе).
4. **Датасеты: 4 ядровых** (`employees_training`, `incidents`, `risks`, `ppe_warehouse`) + декларативный реестр; остальные 4 из каталога — механический follow-up.
5. **Расписания: только run-now.** Cron-исполнение (celery beat) и email-доставка — follow-up.
6. **Архитектура: вариант A** — новый модуль `report_builder` поверх существующего ExportJob-конвейера.

## 3. Не-цели (осознанно отложено)

- Датасеты `inspections_prescriptions`, `documents_edo`, `billing_usage`, `workflow_tasks` (реестр делает добавление механическим).
- Cron-исполнение `ExportSchedule`, email/webhook-доставка (`target_type` остаётся `file`).
- Графики/heatmap в конструкторе (уйдут в срез управленческих дашбордов вместе с chart-библиотекой).
- Подключение существующей кнопки `ReportsPage` (`export_type="reports:xlsx|pdf"`) к материализатору.
- Anonymization profiles из каталога датасетов.
- Tenant-safe sharing UI: `ReportDefinition` tenant-scoped by design (`TenantBaseModel`), внутри тенанта доступ по ролям — расширенный sharing не строим.
- RBAC-дыра `modules/analytics` + дубль-регистрация `operational_dashboard` в `route_groups.py:148,151` — **пре-существующие дефекты вне среза** (вынесены отдельной задачей).

## 4. Модель данных — миграция `rb01` (чисто аддитивная, от head `med03`)

Таблица `report_definition` (`TenantBaseModel` + `SoftDeleteMixin`):

| Поле | Тип | Примечание |
|---|---|---|
| `name` | String(255) NOT NULL | uniq `(tenant_id, name)` без фильтра deleted_at (паттерн `PPESupplier`: soft-deleted тёзка → 409) |
| `description` | Text NULL | |
| `dataset_code` | String(64) NOT NULL | ключ реестра датасетов |
| `config_json` | JSON NOT NULL default `{}` | см. §5 |
| `is_system` | Boolean NOT NULL default False | «готовые шаблоны» из ТЗ; неизменяемые |

Enum'ов в БД нет (статусы job — существующие строки `ExportJob`). PG16-гейт: upgrade/downgrade round-trip.

## 5. Схема `config_json` (валидируется engine'ом, не БД)

```json
{
  "columns": ["person_name", "course_name", "expires_at"],
  "filters": [{"field": "status", "op": "eq", "value": "completed"}],
  "sort": [{"field": "expires_at", "dir": "desc"}],
  "group_by": ["department"],
  "aggregates": [{"fn": "count"}, {"fn": "sum", "field": "quantity"}]
}
```

- Операторы по типу колонки: `string` → `eq/neq/contains`; `number/date/datetime` → `eq/gte/lte`; `enum` → `eq/in`; `bool` → `eq`.
- `group_by` непустой ⇒ выходные колонки = группировочные поля + агрегаты (`columns` игнорируется, UI это отражает); `sum.field` обязан быть агрегируемой (number) колонкой.
- Неизвестное поле/оператор/датасет/формат → 422 со структурной ошибкой (какое поле).
- Sort — только по whitelist колонок датасета (в group-режиме — по группировочным полям и агрегатам).

## 6. Модуль `backend/app/modules/report_builder/`

- **`datasets.py`** — декларативный реестр: `ColumnSpec(key, label_ru, kind, aggregatable)`, `DatasetSpec(code, title_ru, columns, build_stmt(tenant_id))` + `DATASETS: dict[str, DatasetSpec]`. Датасеты MVP (точные колонки пинуются в плане):
  - `employees_training` — `Training` × `Person` (`models/training.py:48`): ФИО, должность, курс (`course_name`), статус, `scheduled_at`, `completed_at`, `expires_at`, признак «просрочено» (вычислимая date-колонка сравнением `expires_at` с now — как выражение в SELECT, чтобы фильтр/группировка работали в SQL).
  - `incidents` — `Incident` (`models/incidents.py:73`): номер/заголовок, тип, статус, тяжесть, дата, объект.
  - `risks` — `Risk` (`models/risk.py:228`): название, уровень, статус, карта/объект.
  - `ppe_warehouse` — `PPEItem` × агрегат остатков по `PPEStockBatch` (`models/ppe.py`): позиция, категория, остаток, `min_stock`, признак «ниже минимума».
  - Soft-delete фильтры у моделей с `SoftDeleteMixin` обязательны; tenant-scope во всех select'ах.
- **`engine.py`** — единый исполнитель preview и экспорта: `run_report(session, tenant_id, dataset_code, config, limit) -> ReportResult(columns_meta, rows, total)`. Валидация §5; фильтры/GROUP BY/агрегаты/sort — на уровне SQL (без выгрузки всего в Python). Preview: `limit=100` + `total` отдельным count. Экспорт: hard cap **50 000 строк**; при превышении — job `failed` с кодом `row_limit_exceeded` (не молчаливое усечение).
- **`renderers.py`** — `rows → bytes`:
  - CSV: `;`-разделитель (консистентно с reorder-CSV на `WarehousePage`), UTF-8 BOM (Excel-RU), экранирование ячеек.
  - XLSX: openpyxl, лист = название отчёта, первая строка — RU-заголовки.
  - PDF: python-docx таблица (landscape A4) → `convert_docx_bytes` (LibreOffice pool). Недоступен LibreOffice → исключение наружу (материализатор переводит job в `failed`, код `pdf_renderer_unavailable`).
- **`service.py`** — CRUD definitions + `run` (создаёт `ExportJob` через `ExportCenterService.create_job(export_type="report", dataset_code, scope_json={"definition_id", "format"}, filters_json=config)` и ставит celery-задачу `.delay(job_id, tenant_id)`) + `preview` (inline-конфиг). Ошибки: `ReportDefinitionNotFound`, `SystemDefinitionImmutable`, `ReportNameConflict` (IntegrityError → 409).
- **`api.py`** — router `prefix="/report-builder"`, регистрация в `route_groups.py` (группа document_core), фичефлаг + RBAC (§7).

## 7. API-контракты

Все роуты за фичефлагом `report_builder` — default-off: `is_feature_enabled(..., default=False)` → 404 со структурным `api_problem_detail` (точный паттерн — committees, `routes/committees.py:85`); demo-сид включает флаг для demo-тенанта. RBAC (ABAC, зеркало `_REPORT_ROLES` из `routes/reports.py:31`): read/preview/run = `admin, owner, ot_specialist, line_manager`; write = `admin, owner, ot_specialist`. Audit-логирование на write и run. Cross-tenant → 404.

| Метод + путь | Что делает | Коды ошибок |
|---|---|---|
| GET `/report-builder/datasets` | реестр: code, title, колонки (key/label/kind/aggregatable/ops) | — |
| GET `/report-builder/definitions` | список (ETag через `compute_list_etag`, 304) | — |
| POST `/report-builder/definitions` | создать | 409 дубль имени, 422 битый config/датасет |
| GET `/report-builder/definitions/{id}` | деталь | 404 |
| PATCH `/report-builder/definitions/{id}` | обновить (allowlist полей) | 400 `system_definition_immutable`, 404, 409, 422 |
| DELETE `/report-builder/definitions/{id}` | soft-delete | 400 system, 404 |
| POST `/report-builder/preview` | inline `{dataset_code, config}` → `{columns, rows(≤100), total}` | 422 |
| POST `/report-builder/definitions/{id}/run` | `{format: csv\|xlsx\|pdf}` → 201 `ExportJob` (id, status) | 404, 422 формат |

Скачивание/статус — существующие `GET /exports/{job_id}` и `GET /exports/{job_id}/download-link` (не трогаем).

## 8. Материализатор — `backend/app/celery/tasks/report_export_job.py`

Задача `app.tasks.report_export_job(job_id, tenant_id)`, зеркало `audit_export_job.py`:

1. `tenant_context` + `ensure_tenant_schema` + `session_scope`; загрузка `ExportJob` (tenant guard `assert_tenant_row_matches_session`); нет/не `report` → `{"status": "missing"}`.
2. `status="running"` → резолв `ReportDefinition` по `scope_json.definition_id` (удалена/нет → `failed`, код `definition_missing`).
3. `engine.run_report(limit=hard_cap)` → renderer по `scope_json.format`.
4. `FileStorageService.default().put(f"{tenant_id}/exports/reports/{job_id}.{ext}", body, content_type)` + строка `File` (bucket `generated`, sha256, size, mime, `original_name="<имя отчёта>.<ext>"`).
5. `job.file_id`, `row_count`, `progress_percent=100`, `status="done"`.
6. Любая ошибка → `status="failed"`, `error_payload={"code", "message"}` (PDF → `pdf_renderer_unavailable`; перекап → `row_limit_exceeded`).

В dev/тестах celery eager (`settings.celery_eager`) — `.delay` исполняется инлайн; тесты зовут task-функцию напрямую (паттерн audit).

## 9. Demo-сид (идемпотентный, паттерн committees `demo_bootstrap.py:698`)

- `Feature(code="report_builder", title="Конструктор отчётов")`.
- 4 системных `ReportDefinition` (`is_system=True`), по одному на датасет: «Просроченное обучение», «Открытые инциденты за период», «Реестр рисков (высокие)», «Остатки СИЗ ниже минимума».

## 10. Frontend

- **`frontend/src/api/reportBuilder.ts`** + DTO `frontend/src/types/dto/reportBuilder.ts`: `listDatasets`, `listDefinitions`, `createDefinition`, `updateDefinition`, `deleteDefinition`, `preview`, `runDefinition`, `getExportJob(id)` (GET `/exports/{id}`), `getDownloadLink(id)` + скачивание blob'ом через `downloadBlob` (GET `download_url`, `responseType:"blob"`).
- **`ReportBuilderPage`** (`frontend/src/pages/reports/ReportBuilderPage.tsx`, house-style single-file, RU-строки):
  - Секция «Сохранённые отчёты»: таблица (имя, датасет, badge «Системный», действия: открыть / дублировать / удалить с confirm; системные — только открыть/дублировать).
  - Секция «Конструктор»: селект датасета → чекбоксы колонок → динамические строки фильтров (поле/оператор по типу/значение) → группировка (мультиселект полей) + агрегаты (count всегда; sum по агрегируемым) → сортировка. При активной группировке блок выбора колонок скрывается (§5).
  - «Предпросмотр» → таблица ≤100 строк + «всего: N». Пустой результат → EmptyState.
  - «Сохранить» / «Сохранить как» (имя + описание), дубль имени → инлайн-ошибка.
  - «Экспорт CSV/XLSX/PDF» → `run` → инлайн-статус с поллингом `getExportJob` (интервал ~1.5 с, таймаут ~60 с) → `done` → кнопка «Скачать»; `failed` → RU-сообщение по `error_payload.code` (отдельный текст для `pdf_renderer_unavailable`).
  - Состояние — `useAsyncResource` для списков; поллинг — локальный `setInterval` с очисткой (guard от двойного запуска, latest-wins).
- **Роутинг:** `/reports/builder` за `REPORTS_VIEW` (`routeGroups.tsx` группа REPORTS_VIEW, lazy в `pageRegistry.tsx`), пункт «Конструктор отчётов» в `navigationConfig.ts` (группа «Бизнес и аналитика»), кнопка-ссылка с `ReportsPage`.

## 11. Тест-план

Backend (`tests/`):
- Юнит engine: фильтры по типам, группировка+агрегаты, sort-whitelist, 422-валидации, preview limit+total, tenant-изоляция, soft-delete фильтры.
- Юнит renderers: CSV (`;`, BOM, экранирование), XLSX (openpyxl round-read), PDF — мок `convert_docx_bytes` (реальный LibreOffice в юнитах не гоняем; graceful-ветка покрыта).
- API: CRUD (+409 дубль, 400 system-immutable, 404 cross-tenant/нет, 422 config), preview, run→201+job, флаг off→404, RBAC (403 запрещённой роли).
- Материализатор: прямой вызов task-функции — file создан в storage, `File`-строка, `job.done/file_id/row_count`; `definition_missing`; формат-ошибки.
- Миграция `rb01`: пин unique-констрейнта и server-default'ов (substring-ассерты whitespace-insensitive — black-грабли).
- Demo-сид: идемпотентность (второй прогон не плодит дубли).

Frontend (vitest): api-клиент (пути/параметры), страница — рендер списка/конструктора, добавление-удаление фильтра, preview-таблица, save/duplicate, экспорт с поллингом (fake timers) success+failed, RBAC-агностично (страница за роутом).

## 12. Гейты верификации (local-evidence, порядок из грабель предыдущих сессий)

1. Точечный pytest батчами ≤5 файлов (PowerShell, глобальный Python313, таймаут 600000 мс, ОДИН прогон; Git-Bash сегфолтит).
2. ruff + black; после black — re-run migration-тестов.
3. OpenAPI baseline re-snap (`scripts/ci/check_openapi_snapshot.py --snapshot`, `$env:PYTHONPATH="backend"`; ожидаем чистый аддитив: +8 роутов + схемы) + compare.
4. PG16-гейт `scripts/ci/local_gate.py --db-only` (Docker): ARCH-3 + alembic round-trip вкл. `rb01` + enum guards.
5. Frontend: точечный vitest → полный `vitest run` (НЕ параллельно с pytest) → `tsc --noEmit` → `vite build`.

## 13. Риски / грабли

- **PDF в тестах:** LibreOffice может отсутствовать локально — юниты мокают конвертер; graceful-ветка (`failed` + код) обязана быть покрыта.
- **JSON-фильтры в idempotency:** `create_job` сверяет `filters_json` — для report-джобов кладём туда config (детерминированная сериализация).
- **Вычислимые колонки** («просрочено», «ниже минимума») — только как SQL-выражения, иначе фильтр/группировка по ним не работают.
- **Полный vitest** флейкает под CPU-контеншном — красное перепроверять в изоляции.
- **Worktree:** нет `node_modules` → `npm ci --prefer-offline` один раз контроллером; backend — глобальный Python313.
