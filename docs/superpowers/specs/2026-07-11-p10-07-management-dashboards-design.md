# P10-07 Управленческие дашборды (§24.2) — design spec

- **Дата:** 2026-07-11
- **Статус:** approved (brainstorming через AskUserQuestion, 5 решений + одобрение дизайна)
- **Ветка:** `feat/p10-07-management-dashboards` от `main@3342b7de` (merge PR #731). PR #732 (report-builder) не ждём: пересечение только в nav/router-файлах, конфликт тривиален.
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B.23 → `PLATFORM_VNEXT_UPGRADE_SPEC.md` §24.2 (управленческие дашборды). Roadmap: P10-07 «Остаётся: управленческие дашборды».

## 1. Контекст (сверка код↔ТЗ, из разведки 2026-07-10)

Уже в `main`:
- `modules/analytics`: 11 dashboard-эндпоинтов `/analytics/dashboard/{executive,safety,client-delivery,incidents,inspections,prescriptions,overdue,sla-load,edo,ppe,training}` + 6 trend-series `/analytics/trends/{incidents,compliance,packages,trainings,inspections,ppe}` (`{metric, period, series:[{date,value}]}`, period=daily/weekly/monthly, 12 точек) + `POST /analytics/recompute`. Все принимают общие фильтры `_filters` (company_id, site_id, contractor_id, status, risk_level, date_from, date_to). Питаются read-models (`modules/projections`) + live-каунтерами `AnalyticsAggregationService.{base_counters,detailed_counters}`.
- **Дыры:** analytics-роутер БЕЗ RBAC и БЕЗ фичефлага (управленческие KPI видны любому аутентифицированному пользователю тенанта); export_center-роутер тоже без RBAC; `operational_dashboard.router` зарегистрирован дважды (`route_groups.py:148,151` — даёт «Duplicate Operation ID» warning в OpenAPI).
- Frontend: суб-дашборды — однострочные обёртки `DashboardApiPage` (generic `getByEndpoint`) → `JsonKpiGrid` (плоский `String(value)`-дамп); маршруты `/dashboard/{executive,safety,training,ppe,client-delivery}` «сиротские» (вне навигации); `TrendsPage` показывает один incidents-тренд числами; **фильтры backend'а фронт не передаёт вообще**; chart-библиотек в проекте нет.

## 2. Решения (зафиксированы пользователем)

1. **Объём = хаб + breakdown**: страница «Управленческая аналитика» (фильтры + KPI + графики трендов) + ОДИН новый backend-эндпоинт breakdown (по компаниям/объектам/подрядчикам) + вывод сиротских суб-дашбордов в достижимость.
2. **Chart-слой = recharts** (новая зависимость; ~100KB gz к бандлу — осознанно; пригодится follow-up'у «графики в конструкторе» §24.3).
3. **RBAC-хардening — первой задачей волны** (analytics + export_center + дубль-регистрация); чип task_5f3fcf25 после реализации отклоняется как superseded.
4. **Размещение = хаб `/analytics`** (новая страница, паттерн секций WarehousePage) + пункт в «Бизнес и аналитика»; сироты — карточками-ссылками с хаба (в навигацию их не выводим, чтобы не раздувать меню).
5. **Breakdown = вариант A**: вычисляемый SQL group-by эндпоинт (без персистенса/миграций/celery).

## 3. Не-цели (осознанно отложено)

- Пере-вёрстка 5 существующих `DashboardApiPage`-страниц (остаются на `JsonKpiGrid`).
- «Активность пользователей» и «состояние системы» из §24.2 (нет агрегаторов — отдельный под-срез), бюджет-виджет (§12.4).
- ETag/Redis-кэш на analytics-эндпоинтах; per-entity снапшоты в проекциях (вариант C — при масштабе).
- Графики в конструкторе отчётов (§24.3 follow-up, но recharts уже будет в проекте).
- Saved views/фильтры дашборда; экспорт дашборда в PDF.

## 4. Задача 1 — RBAC-хардening (backend, без миграций)

- **`modules/analytics/api.py`**: ABAC-зависимость на ВСЕ GET-роуты. **Поправка после сверки матрицы:** `DASHBOARD_VIEW` на фронте выдан ВСЕМ ролям (гейт рабочего стола) — якорем быть не может. Read-роли = union backend-прецедентов (`_SUMMARY_ROLES` dashboard.py + `_OPS_DASHBOARD_ROLES` operational_dashboard.py + `_REPORT_ROLES` reports.py): **admin, owner, hr, ot_pb_lead, line_manager, ot_specialist, manager**. `POST /analytics/recompute` — только admin/owner. Паттерн — `abac(_tenant_resource_id, required_roles=..., action=...)` как в `routes/reports.py:38-41`. Существующие «сиротские» суб-дашборды остаются под фронтовым `DASHBOARD_VIEW` — не-management роль при прямом заходе получит ErrorState (доступ им и не предполагался; документируется).
- **`modules/export_center/api.py`**: read-роуты (GET list/datasets/schedules/kpis/{id}/download-link) — роли по `REPORTS_VIEW`-матрице permissions.ts; write (POST /exports, /schedules, /schedules/{id}/run-now, /kpis, /{id}/retry) — роли, покрывающие фактических потребителей: `queueExport` на ReportsPage доступен при `DOCUMENT_EXPORT || REPORTS_VIEW` → write-роли = union соответствующих ролей (пин в плане). Не сломать: `ExportsPage`/`ReportsPage` (их роли обязаны остаться в списках) и поллинг `GET /exports/{job_id}` со страницы конструктора (read-роли ⊇ report-builder read-роли).
- **`api/v1/route_groups.py`**: убрать дубль-регистрацию `operational_dashboard.router` (строки ~148 и ~151 — оставить одну), проверить что `/operational/dashboard` жив (тест Command Center-роута).
- Тесты: 403 для роли вне списка (worker), 200 для разрешённых; recompute 403 для line_manager; дубль-регистрация — пин через OpenAPI paths (один operationId) или прямой тест реестра роутов.
- После мержа волны чип task_5f3fcf25 отклонить (superseded).

## 5. Задача 2 — breakdown-эндпоинт (backend, без миграций)

`GET /analytics/dashboard/breakdown?dimension=company|site|contractor` (+ `date_from`/`date_to` из общих `_filters`; фильтры company_id/site_id/contractor_id к breakdown не применяются — измерение и есть разрез).

- **Семантика:** для каждой сущности измерения в тенанте — набор метрик. Метрики MVP (пин точных выражений в плане по фактическому `AnalyticsAggregationService.detailed_counters`): `incidents_open`, `prescriptions_overdue`, `trainings_overdue`, `risks_high`, `ppe_overdue`. Каждая метрика — ОДИН SQL `SELECT <dim_id>, count(*) ... GROUP BY <dim_id>` (без N+1), сшивка по id в Python; имена — join master-data (`Company.name`/`Site.name`/`Contractor.name`).
- **Ответ:** `{dimension, items: [{id, name, incidents_open, prescriptions_overdue, trainings_overdue, risks_high, ppe_overdue, total_issues}], total}`; `total_issues` = сумма метрик строки; сортировка `total_issues desc, name asc`; cap 200 строк (`total` — фактическое число сущностей). Сущности без единой метрики включаются с нулями (управленец должен видеть «чистые» филиалы) — источник списка сущностей: master-data таблица измерения (tenant-scoped, deleted_at IS NULL где применимо).
- **Ошибки:** неизвестный `dimension` → 422 (`api_problem_detail`). RBAC/тенант — как у остальных analytics-роутов (Задача 1).
- **Date-фильтры:** применяются к метрикам, где есть датируемое поле (incidents.occurred_at; prescriptions/trainings по их due/дате — пин в плане); метрики без применимой даты игнорируют период (документируется в docstring).
- Не-цель: contractor-разрез метрик, не имеющих связи с подрядчиком — такие метрики в contractor-разрезе отдают 0 (пин в плане по фактическим FK; допустимо вернуть подмножество метрик — тогда фронт рендерит только пришедшие ключи).
- Тесты: сид 2 объекта с разными инцидентами/предписаниями → верные разрезы и сортировка; сущность с нулями присутствует; tenant-изоляция; 422; date-окно сужает счётчики.

## 6. Задача 3 — chart-слой (frontend)

- `recharts` (^2.x) в `frontend/package.json` (единственная новая зависимость волны).
- `frontend/src/components/analytics/TrendLineChart.tsx`: пропсы `{title, series: {date, value}[], loading?}`; `ResponsiveContainer` + `LineChart` (одна линия, RU-тултип, ось X — короткая дата); пустая серия → EmptyState-текст.
- Breakdown-бары: внутри таблицы разреза (инлайн `<div>`-бар шириной % от max — без recharts: таблица читабельнее для сравнения сущностей; recharts — для трендов). Если в плане окажется дешевле BarChart — допустимо, но таблица с числами обязательна.
- Тестируемость: jsdom не даёт размеров — в тестах проверяем заголовки/значения/наличие серий, не пиксели; при необходимости ResizeObserver-мок в setup (проверить house-setup `frontend/src/setupTests.ts` — возможно уже есть).

## 7. Задача 4 — страница `/analytics` «Управленческая аналитика» (frontend)

- **`frontend/src/api/analyticsApi.ts`** (типизированный, вместо generic `dashboardApiClient`): `getDashboard(name, filters)` (executive/overdue/sla-load — используемые хабом), `getTrend(metric, period, filters)`, `getBreakdown(dimension, filters)` + DTO (`frontend/src/types/dto/analytics.ts`). Фильтры: `{company_id?, site_id?, contractor_id?, date_from?, date_to?}` → query-params.
- **`frontend/src/pages/analytics/ManagementDashboardPage.tsx`** (house-style single-file, RU):
  1. **Фильтр-бар**: селекты «Компания» / «Объект» / «Подрядчик» (списки из существующих master-data list-эндпоинтов — пин методов в плане по фактическим api-клиентам) + период (date_from/date_to) + «Сбросить». Смена фильтра → reload всех секций (useAsyncResource, loader зависит от фильтров — latest-wins уже в хуке).
  2. **KPI-секция**: карточки из `executive` (widgets+dashboard counters) + `overdue` + `sla-load` — число + RU-подпись (набор карточек пинуется в плане по фактическим ключам ответов; неизвестные ключи не рендерим — не JsonKpiGrid-дамп).
  3. **Секция «Тренды»**: грид 6 × `TrendLineChart` (incidents/compliance/packages/trainings/inspections/ppe), общий toggle daily/weekly/monthly (aria-pressed, паттерн MedicalPage).
  4. **Секция «Разрез»**: toggle «По компаниям / По объектам / По подрядчикам» → таблица (Название | метрики | Всего проблем с инлайн-баром от max); строка-сущность кликабельна → применяет её как фильтр страницы (drill-down).
  5. **Карточки «Профильные дашборды»**: ссылки на `/dashboard/{executive,safety,training,ppe,client-delivery}` (сироты становятся достижимыми).
- **Wiring**: НОВОЕ фронтовое право `ANALYTICS_VIEW: "analytics.view"` в `permissions.ts` (роли: owner/admin/ot_pb_head — через ALL_PERMISSIONS автоматически; явно добавить ot_specialist, line_manager, hr — зеркало backend-списка; worker/client/студенты НЕ получают — иначе пункт меню вёл бы на страницу из 403). `pageRegistry` lazy + `routeGroups` (новая группа `ANALYTICS_VIEW`, путь `/analytics`) + `navigationConfig` пункт «Управленческая аналитика» в «Бизнес и аналитика» за `ANALYTICS_VIEW`. ВНИМАНИЕ: путь `/analytics` не должен перехватить `/analytics/trends` (существующий) — Route точный, не wildcard.
- Ошибки: per-секционные ErrorState (страница не падает целиком); 403 (не-management роль) → ErrorState секций.

## 8. Тест-план

- Backend: RBAC-матрица analytics (worker 403 / admin+line_manager 200 / recompute line_manager 403) + export_center (роли из матрицы; существующие тесты export_center не должны сломаться — поправить их auth, если гоняются без ролей); breakdown — 5 тестов из §5; smoke одного существующего analytics-эндпоинта под новой RBAC (регресс test_analytics*, если есть — найти и прогнать).
- Frontend: analyticsApi (пути/params, фильтры сериализуются), ManagementDashboardPage (фильтры пробрасываются во все вызовы; тренды рендерят 6 заголовков; toggle периода меняет параметр; breakdown-таблица + смена dimension; клик по строке применяет фильтр; ссылки на суб-дашборды), TrendLineChart smoke (заголовок/empty).
- Регресс: `DashboardVariantsStates.test.tsx` (generic-страницы), `ReportsPage`/`ExportsPage` тесты (RBAC export_center не сломал фронт — они мокают api, так что риска нет; проверить backend-тесты exports, если существуют).

## 9. Гейты верификации (порядок прежний)

1. Точечный pytest батчами ≤5 (PowerShell, Python313, таймаут 600000, ОДИН прогон).
2. ruff + black.
3. OpenAPI baseline re-snap: ожидание — +1 роут (breakdown) + схемы, МИНУС один дубль-operationId operational_dashboard (диф НЕ чисто аддитивный из-за снятия дубля — это ожидаемо, зафиксировать в handoff) + compare exit 0.
4. PG16-гейт НЕ нужен (миграций нет); ARCH-3 не затрагивается.
5. Frontend: точечный vitest → полный (НЕ параллельно с pytest) → tsc → build (отметить дельту размера бандла от recharts).

## 10. Риски / грабли

- **RBAC-ролевые списки**: единственный реальный риск волны — отрезать существующего легитимного потребителя. Митигция: списки выводятся из permissions.ts-матрицы (кто видит страницу — тот имеет роль в backend-списке), пин в плане, регресс существующих тестов analytics/exports.
- **recharts в jsdom**: ResponsiveContainer без размеров может рендерить пусто — тесты на данные/заголовки, не на SVG-геометрию; ResizeObserver-мок при необходимости.
- **`/analytics` vs `/analytics/trends`**: проверить порядок/точность Route (react-router v6 — точные пути, риска мало, но тест на оба маршрута обязателен).
- **Breakdown на больших тенантах**: 5 GROUP BY-запросов — дёшево; cap 200 строк; сортировка в SQL не обязательна (метрики сшиваются в Python — сортировка там же).
- Worktree: нет node_modules → `npm ci --prefer-offline` контроллером фоном ДО фронт-групп; `npm i recharts` меняет package-lock — коммитить вместе с package.json.
