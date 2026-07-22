# P10-01 Комитеты, срез-3 — KPI-дашборд + проекция задач в Command Center — design spec

- **Дата:** 2026-07-22
- **Статус:** approved (scope + 2 решения зафиксированы пользователем через AskUserQuestion)
- **Ветка:** `feat/p10-01-committees-srez3-kpi-command-center` от `main` (head `66aca700`, срез-2 уже влит — PR #751).
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B.17 → «Комитеты …, приглашения, протоколы, решения, голосование, задачи, **KPI исполнения**». Roadmap: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` строка P10-01 → остаток срез-3: «приглашения на заседание, **KPI-дашборд комитетов**, **проекция задач в Command Center**, настраиваемый порог кворума, печатная форма протокола, серверный person-typeahead».
- **Аддитивно:** новых таблиц/миграций НЕТ. Все метрики считаются из существующих таблиц срез-1/срез-2 (в т.ч. денормализованных `members_total/present_count/quorum_met` на `committee_meeting`).

## 1. Контекст (сверка код↔ТЗ)

Срез-1 (PR #695) и срез-2 (PR #751) в `main`:
- Модели `backend/app/models/committees.py`: `Committee` (soft-delete), `CommitteeMember`, `CommitteeMeeting` (status planned/held/cancelled, soft-delete, снапшот `held_at/protocol_seq/protocol_year/members_total/present_count/quorum_met`), `CommitteeAgendaItem`, `CommitteeDecision`, `CommitteeDecisionTask` (status open/in_progress/done, `due_date`, **без** soft-delete), `CommitteeMeetingAttendance`, `CommitteeDecisionVote`.
- Чистые правила `domains/committees/lifecycle.py`: `is_task_overdue`, `is_quorum`, `tally_votes`, `decision_outcome`.
- Command Center = **Operational Dashboard** (`backend/app/modules/operational_dashboard/`): единый snapshot-сервис `OperationalDashboardService.get_dashboard`, хардкод-список приватных источников `_get_*_alerts → list[AlertItem]`. Категории — enum `AlertCategory` (`schemas.py`). Фронт `components/operational/CommandCenterPanel.tsx` группирует по категории, метки в `CATEGORY_LABELS_RU`.
- Управленческие дашборды P10-07 (`modules/analytics/`): роли-читатели `_ANALYTICS_READ_ROLES = [admin, owner, hr, ot_pb_lead, line_manager, ot_specialist, manager]`.

**Дыры относительно ТЗ (срез-3, этот срез закрывает 2 из 6):** нет KPI-дашборда комитетов; задачи комитетов не видны в Command Center.

## 2. Решения (зафиксированы пользователем через AskUserQuestion)

1. **Объём срез-3 = KPI-дашборд + проекция задач в Command Center.** Приглашения, настраиваемый порог кворума, печатная форма протокола, серверный person-typeahead — осознанно в срез-4.
2. **Аудитория KPI-дашборда = управленческая** (не только admin). RBAC на бэке — переиспользуем `_ANALYTICS_READ_ROLES`; фронт-роут и nav гейтим по `ANALYTICS_VIEW` (право есть у руководителей: hr/line_manager/ot_specialist), в отличие от `COMMITTEE_VIEW` (только admin/owner/ot_pb_head). Так «кто видит дашборды» = «кто видит KPI комитетов».
3. **Проекция в Command Center = отдельная категория** `committee_task` (own card «Задачи комитетов»), а не подмешивание в существующие `overdue`/`unassigned_task`.

## 3. Не-цели (осознанно отложено в срез-4)

- Приглашения на заседание (email/notification членам).
- Настраиваемый порог кворума / квалифицированное большинство.
- Печатная форма протокола DOCX/PDF.
- Серверный person-typeahead.
- Тренды/сравнение по периодам и breakdown по объектам/комитетам в KPI (v1 — плоские агрегаты + опц. фильтр `committee_id`).
- Проекция задач комитетов в поисковый индекс / dashboard-snapshot (только Operational Dashboard alert-card).

## 4. Данные — без миграции

Метрики берутся из существующих таблиц. Денормализованные поля заседания (`members_total/present_count/quorum_met`) позволяют считать среднюю явку и долю кворума **без джойна** attendance. У `CommitteeDecisionTask` **нет** `deleted_at` — фильтр `deleted_at.is_(None)` НЕ применять (упадёт).

## 5. Backend — KPI

**Новый сервис** `backend/app/domains/committees/kpi.py` — `CommitteeKpiService(session, tenant_id)`, метод `compute(*, committee_id=None, today=None) -> CommitteeKpiDto`. Агрегаты (все `.where(<Model>.tenant_id == tenant_id [, deleted_at.is_(None) для soft-delete-моделей])`):
- `committees_total` / `committees_active` — `Committee` (soft-delete; active = `is_active is True`).
- `meetings_planned/held/cancelled` — `CommitteeMeeting` (soft-delete), один `group_by(status)`.
- `decisions_total` — `CommitteeDecision`.
- `tasks_open` (status != DONE) / `tasks_overdue` (status != DONE AND due_date < today) / `tasks_done` / `tasks_total` — `CommitteeDecisionTask`.
- `avg_attendance_pct` — среднее `present_count/members_total*100` по HELD-заседаниям с `members_total>0` (считаем в Python из выбранных строк — DB-agnostic для SQLite-тестов).
- `quorum_rate_pct` — доля HELD-заседаний с `quorum_met is True` (в %).
- `held_meetings` — знаменатель для двух ставок выше (прозрачность).

Фильтр `committee_id` (опц.): meetings — `committee_id ==`; decisions — join `CommitteeMeeting`; tasks — join `CommitteeDecision`→`CommitteeMeeting`.

**Схема** `backend/app/schemas/committees.py` — `CommitteeKpiDto(BaseSchema)` с явными int-полями и float `avg_attendance_pct`/`quorum_rate_pct` (округление до 1 знака в сервисе).

**Роут** — `@router.get("/kpi", response_model=CommitteeKpiDto)` в `api/routes/committees.py`, **объявлен до `GET /{cid}`** (рядом с `/protocols`, тот же FastAPI order-hazard). Шапка как `list_protocols`: `TenantContextValidator.ensure_tenant_context` + `_require_committees_enabled` (404 при выключенном флаге) + `compute_list_etag`/304. RBAC — отдельный guard `KpiAccess = abac(_tenant_resource_id, required_roles=_KPI_ROLES)`, где `_KPI_ROLES` = копия `_ANALYTICS_READ_ROLES` (management), а не `_ROLES=["admin"]`.

## 6. Backend — проекция в Command Center

**Новая категория** `AlertCategory.COMMITTEE_TASK = "committee_task"` (`modules/operational_dashboard/schemas.py`).

**Новый источник** `_get_committee_task_alerts(self, tenant_id, db) -> list[AlertItem]` (`service.py`), вызывается одной строкой в `get_dashboard` после `_get_unassigned_task_alerts`. Локальный `try/import` (ImportError → `[]`). Два счётчика (title — по стилю существующих источников, англ.; RU-метка категории живёт на фронте):
- overdue: `status != DONE AND due_date IS NOT NULL AND due_date < today` → `AlertItem(category=COMMITTEE_TASK, severity=HIGH, id="committee_tasks_overdue", action_url="/committees")`.
- unassigned: `assignee_person_id IS NULL AND status != DONE` → `AlertItem(category=COMMITTEE_TASK, severity=MEDIUM, id="committee_tasks_unassigned", action_url="/committees")`.
- Без фильтра `deleted_at` (у модели его нет). Флаг committees НЕ проверяем (консистентно с прочими источниками; при выключенном модуле данных просто нет → count 0).

## 7. Frontend

- **API** `api/committees.ts`: тип `CommitteeKpi` + метод `getKpi(params?: {committee_id?})` → `GET /committees/kpi`.
- **Страница** `pages/committees/CommitteeKpiPage.tsx`: fetch по образцу `CommitteesPage` (useEffect/useState, `RegistryPageHeader`, Loading/Error/Empty), карточки метрик с **русскими** метками, сгруппированные (Заседания / Решения / Задачи / Явка и кворум). Ссылка «← К комитетам» (для тех, у кого есть доступ к странице комитетов). При выключенном флаге бэк вернёт 404 → показываем понятный EmptyState.
- **Роутинг** `router/routeGroups.tsx`: `/committees/kpi` в группе `ANALYTICS_VIEW` (React Router v6 ранжирует по специфичности → не конфликтует с `/committees` из группы `COMMITTEE_VIEW`).
- **Nav** `router/navigationConfig.ts`: пункт «KPI комитетов» → `/committees/kpi`, `permission: ANALYTICS_VIEW`. `router/navVisibility.ts`: скрывать `/committees/kpi` при `featureFlags.committees === false` (как `/committees`).
- **pageRegistry.tsx**: lazy-импорт `CommitteeKpiPage`.
- **Command Center** `api/operationalDashboard.ts`: `+ "committee_task"` в union `AlertCategory`. `components/operational/CommandCenterPanel.tsx`: `CATEGORY_LABELS_RU.committee_task = "Задачи комитетов"` + добавить в `CATEGORY_ORDER`.

## 8. Demo-seed

Расширение не требуется: `_seed_committees_demo` уже сеет проведённое заседание (протокол `1/ГГГГ`, явка 3/4, кворум), решение с голосами (принято) и **просроченную неназначенную** задачу. → KPI-дашборд и карточка Command Center сразу с живыми числами в demo-тенанте. (Опц. смоук — не менять сид.)

## 9. Тест-план

**Backend unit (без сессии):** отдельных чистых функций срез-3 нет — переиспользуем `is_task_overdue` и т.п.; unit-логика KPI (проценты, деление на ноль) покрывается через сервис на in-memory сессии conftest.

**Backend API/service (async, tenant-iso):**
- `test_committees_srez3_kpi.py` (НОВЫЙ): пустой тенант → все нули, ставки 0.0 (нет held-заседаний → без деления на ноль); тенант с данными → корректные счётчики; фильтр `committee_id` изолирует; overdue/open задачи считаются по FSM (done не учитывается); avg_attendance/quorum_rate на смешанных заседаниях; tenant-iso (данные другого тенанта не видны); RBAC — management-роль (напр. hr/manager) получает 200, worker → 403; флаг off → 404; ETag/304.
- `test_operational_dashboard.py` (РАСШИРИТЬ): источник `_get_committee_task_alerts` — overdue → HIGH-alert категории `committee_task`; unassigned → MEDIUM; done/назначенные не попадают; tenant-iso; отсутствие committee-данных → нет карточки.

**Frontend (vitest):**
- `committeesApi.srez3.test.ts` (НОВЫЙ): `getKpi` дёргает `/committees/kpi`, прокидывает `committee_id`.
- `CommitteeKpiPage.test.tsx` (НОВЫЙ): рендер карточек из мок-DTO, состояние loading/empty/error, 404-флаг-off → EmptyState.
- `CommandCenterPanel.test.tsx` (РАСШИРИТЬ): alert категории `committee_task` рендерится под меткой «Задачи комитетов».
- Роут-смоук: `/committees/kpi` не роняет AppRouter.

**Гейты (порядок как в прошлых срезах):**
1. Backend-регресс батчами ≤5 файлов (ОДИН прогон, timeout 600000): новые+смежные committees/operational тесты.
2. `ruff check --no-fix` + `ruff format` clean.
3. **OpenAPI baseline** пере-снять (+1 операция `/committees/kpi`, +1 схема `CommitteeKpiDto`); `check_openapi_snapshot.py` = EXIT 0.
4. Frontend: точечный vitest → полный `vitest run` (не параллелить с pytest) → `tsc --noEmit` → `vite build`.
5. Docs: handoff в `AI_IMPLEMENTATION_REPORT.md`, `CHANGELOG.md`, правка roadmap P10-01 (срез-2 → merged; срез-3 → partial, остаток = приглашения/кворум-порог/печать/typeahead), при необходимости `TZ_COVERAGE_MATRIX.md`.

## 10. Риски / грабли

- **`CommitteeDecisionTask` без soft-delete** — не фильтровать `deleted_at`.
- **Деление на ноль** в avg_attendance/quorum_rate — гард `held_meetings == 0 → 0.0`; `members_total>0` в знаменателе явки.
- **FastAPI order-hazard** — `/kpi` объявить до `/{cid}` (иначе `cid="kpi"`).
- **RBAC-рассинхрон фронт↔бэк** — бэк пускает management-роли; фронт-роут под `ANALYTICS_VIEW`, а не `COMMITTEE_VIEW` — иначе «бэк пускает, фронт прячет».
- **Новая `AlertCategory`** — синхронно править enum (бэк), union (фронт), `CATEGORY_LABELS_RU` + `CATEGORY_ORDER` (иначе метка = сырой код).
- **OpenAPI snapshot** нужен env `S3_ACCESS_KEY/S3_SECRET_KEY/SECRET_KEY` (годятся пустышки) — как в срез-2.

## 11. Порядок реализации

1. Схема `CommitteeKpiDto` + сервис `kpi.py`.
2. Роут `/committees/kpi` + management-guard.
3. Command Center: категория + источник.
4. Backend-тесты (KPI + operational).
5. Frontend: API-метод + типы; страница; роут/nav/registry; Command Center category label.
6. Frontend-тесты.
7. Гейты: ruff, OpenAPI baseline, vitest/tsc/build; docs.
