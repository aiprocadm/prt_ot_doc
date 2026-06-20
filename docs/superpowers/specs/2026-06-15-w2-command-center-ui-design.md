# W2 · Command Center UI — design (spec)

- **Дата:** 2026-06-15
- **Статус:** утверждён пользователем (2026-06-15), готов к writing-plans
- **Волна:** W2 (Phase 2 — Operational Dashboard), frontend-остаток
- **Канон:** [`docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`](../../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md) §Phase 2.1; design-roadmap [`2026-05-29-tz-completeness-roadmap-design.md`](2026-05-29-tz-completeness-roadmap-design.md) §W2

---

## 1. Контекст и ключевая находка

W2 в roadmap описана как «Command Center UI (виджеты алертов) + Health-status UI (drill-down) — backend готов».

**Аудит кода 2026-06-15 показал: Health UI уже полностью реализован** и не входит в остаток:
- `frontend/src/pages/admin/HealthStatusPage.tsx` — страница «Состояние системы»
- `frontend/src/components/health/HealthStatusPanel.tsx` — drill-down по сервисам (postgres/redis/minio/workers/integrations/email), статус + `duration_ms` + ошибка, failed-first сортировка
- `frontend/src/stores/health.ts` + `frontend/src/api/health.ts` — потребляют `GET /api/v1/health/comprehensive` (skip_cache/skip_slow)
- Роут `/admin/health` (guard `ADMIN_MANAGE_ROLES`), пункт навигации «Состояние системы»

**Поэтому остаток W2 = только страница Command Center** — потребитель `GET /api/v1/operational/dashboard`, который сейчас **не используется нигде** во фронтенде (grep по `operational/dashboard` / `CommandCenter` → пусто).

## 2. Backend-контракт (готов, не меняем)

`GET /api/v1/operational/dashboard`
- Роли (backend-authoritative): `admin`, `owner`, `hr`, `ot_pb_lead`, `line_manager`, `manager`
- Требует заголовок `X-Tenant-Id` (инжектится `apiClient` автоматически — подтверждено тем, что health-контур с тем же требованием работает)
- Ответ `OperationalDashboardResponse`:
  - `tenant_id: str`
  - `status: "ok" | "warning" | "critical"`
  - `alerts: AlertItem[]`
  - `alert_count: { [severity]: number }`
  - `health_status: str | null`
  - `timestamp: datetime`
- `AlertItem`:
  - `id: str`
  - `category`: `overdue | blocked_approval | integration_error | high_risk | health_warning | unassigned_task | data_quality` (7)
  - `severity`: `critical | high | medium | low` (4)
  - `title: str`
  - `description: str | null`
  - `count: int` (число затронутых сущностей — агрегат на бакет-категорию)
  - `affected_entity_type: str | null`
  - `affected_entity_id: str | null`
  - `action_url: str | null`
  - `created_at: datetime`
  - `expires_at: datetime | null`

Endpoint всегда возвращает 200 (даже при `warning`/`critical`); 400 — при отсутствии tenant-заголовка.

## 3. Решения (утверждены)

- **Структура:** новая отдельная страница «Командный центр». Существующий рабочий стол (`DashboardPage`) и `AttentionPanel` («Центр внимания», источник — `workspaceApi.getAttention`) **не трогаем**.
- **Обновление:** polling каждые **30 секунд** + кнопка «Обновить» + refetch по `visibilitychange` (когда вкладка снова видима). Без WebSocket (нет WS-инфраструктуры; вне frontend-only рамок W2).
- **Guard:** роут в группе `PERMISSIONS.DASHBOARD_VIEW` (как прочие дашборды `/dashboard/*`); ролевой режим обеспечивает backend.
- **Роут:** `/command-center`, пункт навигации «Командный центр» в группе «Документооборот» рядом с «Центр внимания».

## 4. Архитектура и файлы (зеркало health-контура)

| Слой | Новый/изменяемый файл | Образец |
|---|---|---|
| API + DTO-типы | **new** `frontend/src/api/operationalDashboard.ts` | `frontend/src/api/health.ts` |
| Store (polling) | **new** `frontend/src/stores/operationalDashboard.ts` | `frontend/src/stores/health.ts` |
| Презентация | **new** `frontend/src/components/operational/CommandCenterPanel.tsx` (+ внутренняя `AlertCategoryCard`) | `frontend/src/components/health/HealthStatusPanel.tsx` |
| Страница | **new** `frontend/src/pages/operational/CommandCenterPage.tsx` | `frontend/src/pages/admin/HealthStatusPage.tsx` |
| Тест | **new** `frontend/src/__tests__/CommandCenterPanel.test.tsx` | паттерн `HealthStatusPanel` тестов |
| Реестр страниц | **edit** `frontend/src/router/pageRegistry.tsx` (+`CommandCenterPage` lazy) | существующие записи |
| Роуты | **edit** `frontend/src/router/routeGroups.tsx` (route в группе `DASHBOARD_VIEW`) | `/dashboard/*` routes |
| Навигация | **edit** `frontend/src/router/navigationConfig.ts` (пункт в «Документооборот») | «Центр внимания» |

### 4.1 API-слой (`api/operationalDashboard.ts`)
- Экспорт типов: `AlertSeverity`, `AlertCategory`, `AlertItem`, `OperationalDashboardDto` (зеркало backend-схемы, поля как в §2).
- `operationalDashboardApi.getDashboard(): Promise<OperationalDashboardDto>` → `apiClient.get("/operational/dashboard")`.

### 4.2 Store (`stores/operationalDashboard.ts`)
- Zustand + immer; состояние `{ data, loading, error, fetchDashboard(), reset() }` (форма как `useHealthStore`).
- Polling организуется в странице (`setInterval` в `useEffect` с очисткой), а не в store — store остаётся чистым «загрузчиком». (Решение: страница владеет таймером; store идемпотентно перезагружает `data`.)

### 4.3 Презентация (`components/operational/CommandCenterPanel.tsx`)
Чистый презентационный компонент: `CommandCenterPanel({ data, loading, error, onRefresh })`. Не знает про store/сеть → тестируется напрямую.
- **Шапка:** заголовок «Командный центр» + общий `StatusBadge` (`data.status`) + кнопка «Обновить» (иконка `RefreshCw`, `animate-spin` при `loading`).
- **Severity-сводка:** чипы `alert_count` по уровням critical/high/medium/low (скрывать нулевые).
- **Виджеты-категории:** группировка `alerts` по `category`; одна `AlertCategoryCard` на непустую категорию. Порядок категорий — по максимальной severity внутри (failed-first: critical→high→medium→low), затем по RU-лейблу. RU-лейблы:
  - `overdue` → «Просроченные»
  - `blocked_approval` → «Заблокированные согласования»
  - `integration_error` → «Ошибки интеграций»
  - `high_risk` → «Высокий риск»
  - `health_warning` → «Предупреждения системы»
  - `unassigned_task` → «Неназначенные задачи»
  - `data_quality` → «Качество данных»
- **Строка алерта:** severity-иконка (`AlertCircle`/`AlertTriangle`/`Info` по уровню), `title`, `description`, бейдж `count` («N шт.»), ссылка «Перейти» на `action_url` через `<Link>` (рендерить только если `action_url` задан и это internal-путь, т.е. начинается с `/`).
- **Empty state:** при пустом `alerts` — карточка «Нет активных алертов» с `CheckCircle2` (зелёная).
- **Error state:** карточка с текстом ошибки + retry (через `onRefresh`).
- **Loading:** при первой загрузке без данных — «Загрузка…».

### 4.4 Страница (`pages/operational/CommandCenterPage.tsx`)
- Подключает `useOperationalDashboardStore`, в `useEffect` вызывает `fetchDashboard()` и заводит `setInterval(fetchDashboard, 30_000)` с очисткой.
- `visibilitychange`-листенер: при возврате на вкладку — `fetchDashboard()`.
- Рендерит `<Breadcrumb>` + `<CommandCenterPanel ... onRefresh={fetchDashboard}>`.

## 5. Производительность (acceptance Ph2.1: загрузка < 2с при 1000+ элементов)

Агрегатор возвращает по одному `AlertItem` на бакет-категорию с числовым `count`, а не 1000 отдельных строк → DOM лёгкий, виртуализация не нужна. Защитная мера: если категория всё же содержит много `AlertItem`, `AlertCategoryCard` показывает первые **20** строк + кнопку «показать ещё» (постранично, без виртуализации). Это явный, документированный предел — не молчаливое усечение.

## 6. Тестирование

- **Unit (vitest)** на чистую `CommandCenterPanel`:
  - рендер всех непустых категорий с RU-лейблами;
  - severity-сортировка категорий (failed-first);
  - severity-чипы из `alert_count`;
  - empty state при `alerts: []`;
  - error state + вызов `onRefresh`;
  - ссылка «Перейти» рендерится только при валидном internal `action_url`.
- **Smoke:** страница `/command-center` рендерится без падения под guard `DASHBOARD_VIEW` (вписать в существующий smoke-набор, если он перечисляет ключевые роуты).
- Backend не меняется → backend-тесты не затрагиваются.

## 7. Acceptance W2 (Command Center half)

- [ ] Страница `/command-center` доступна операционным ролям, отдаёт виджеты по 7 категориям из `/operational/dashboard`.
- [ ] Polling 30с + ручной refresh + refetch по visibilitychange работают.
- [ ] Severity-сводка, empty/error/loading состояния, ссылки «Перейти» по `action_url`.
- [ ] Guard `DASHBOARD_VIEW`; ролевой режим — на backend.
- [ ] Unit-тесты панели зелёные; smoke роута проходит.
- [ ] Health UI остаётся нетронутым и рабочим (regression-sanity).

## 8. Вне объёма (явно отложено)

- WebSocket realtime (требует backend WS-эндпоинта).
- Изменения backend `/operational/dashboard` или health-эндпоинтов.
- Унификация `AttentionPanel` ↔ Command Center (два источника алертов сосуществуют; слияние — отдельное product-решение).
- i18n (UI на русском, как весь текущий фронт).

## 9. Правила доработки (§E канона)

Не ломать рабочие модули (Health UI, DashboardPage, AttentionPanel); следовать существующим паттернам слоёв api/store/component/page; строгая типизация TS; русский UI; permission-guard на роуте.
