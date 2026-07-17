# Бюджет безопасности — кросс-доменный контур §12.4, срез-1 «ядро» — Design

**Дата:** 2026-07-17
**Контур:** кросс-доменный §12.4 «Бюджетный контур» (ТЗ `PLATFORM_VNEXT_UPGRADE_SPEC.md §12.4`,
`TZ_FULL_UNIFIED.md:369` B.11 `[v1.1]`; roadmap: «отдельный под-проект» в next-up).
**Предшественник (влит в main):** СИЗ-часть §12.4 — `PPESafetyBudget` + `batch.unit_cost` (`wa09`,
план↔факт закупок СИЗ, спека `2026-07-05-p10-06-ppe-safety-budget-design.md`). Этот срез **не трогает**
СИЗ-контур — обобщает подход на остальные домены.
**Driver:** brainstorming → writing-plans → subagent-driven-development.
**Head-миграция на старте:** `20260715_re01_automation_rules` (единственный head, в main). Новая
миграция `bg01` чейнится от неё.
**База ветки:** `main`@`bbf8e628` (merge PR #751); ветка `claude/tz-continuation-d43adc`
(изолированный worktree `tz-continuation-d43adc`).

## Цель

Дать платформе единый контур **«Бюджет безопасности»**: план расходов по доменам
**обучение / медосмотры / мероприятия** (СИЗ уже есть), **журнал фактических расходов** со
**статьями расходов** и измерениями (компания/филиал/объект), **контроль план↔факт** и
**аналитику по филиалам и объектам** — включая сводку, в которой виден и СИЗ-контур (read-only).

Инвариант эталонного СИЗ-среза сохраняется дословно: **план персистентен, факт всегда вычисляется
из журнала** (здесь журнал = `budget_expense`; для СИЗ — складской леджер). Ничего не денормализуем,
складской учёт не затрагиваем (acceptance §35.5 / F.5 «бюджет не конфликтует со складским учётом»).

## Принятые решения (brainstorming, 2026-07-17, AskUserQuestion)

1. **Объём = ядро без возмещений:** бюджеты 3 доменов + статьи расходов + журнал расходов +
   план↔факт + аналитика по филиалам/объектам. **Заявки на возмещение (СФР) — срез-2** (отдельный
   workflow со статусами; отклонён «полный §12.4 одной волной» — волна станет ~+3-4 задачи;
   отклонён «минимум только бюджеты» — §12.4 остался бы открыт ещё на 2 среза).
2. **Факт = журнал расходов** (новая сущность `budget_expense`: дата/сумма/статья/домен/измерения +
   опциональная ссылка на доменную сущность). Отклонены: cost-поля в доменных моделях
   (правки в 3 чужих доменах, статьи некуда класть, расходы без сущности — аренда зала, услуги —
   не учесть) и связка с CRM-финансами (`finance.Contract/Invoice` — ручные CRM-документы без
   связей с ОТ-доменами, гранулярность договора ≠ гранулярность расхода, чужой accountant-RBAC).
3. **СИЗ-бюджет остаётся как есть, читается в сводке read-only:** `ppe_safety_budget` /
   `/ppe/budgets` / секция WarehousePage не трогаются; `GET /budget/overview` подтягивает СИЗ-план
   из `ppe_safety_budget` и СИЗ-факт через существующий `compute_budget_actual` (склад-леджер).
   Ноль миграций данных, ноль ломаных API. (Отклонены: обобщить-и-мигрировать; независимые контуры.)
4. **Статьи расходов = tenant-редактируемый справочник с предзаполнением дефолтов**
   (`POST /budget/articles/seed-defaults`, идемпотентно — паттерн психиатрического каталога 342н).
   Отклонён фиксированный список в коде.

## Архитектура

### Слой 1 — модели `backend/app/models/budget.py` (новый файл, 3 таблицы)

Все — `TenantBaseModel + SoftDeleteMixin`. Домены и прочие enum-подобные колонки — **VARCHAR, не
PG-enum** (анти-грабли конвенция ppe.py/medical.py); whitelist в коде модуля.

```python
BUDGET_DOMAINS = ("training", "medical", "events")   # СИЗ ведётся в ppe_safety_budget
EXPENSE_ENTITY_TYPES = {
    "training": "training_session",     # -> TrainingSession
    "medical": "medical_exam",          # -> MedicalExam
    "events": "corrective_action",      # -> safety_ops.CorrectiveAction («Мероприятия (CAPA)»)
}

class SafetyBudget(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "safety_budget"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)   # training|medical|events
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    planned_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # индекс (tenant_id, domain); пересечения периодов допускаются (прецедент СИЗ, YAGNI)

class BudgetExpenseArticle(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "budget_expense_article"
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)  # NULL = универсальная
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # unique (tenant_id, code) БЕЗ deleted_at-фильтра (прецедент rules_engine/report_builder,
    # пин-тест: soft-deleted тёзка блокирует создание)

class BudgetExpense(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "budget_expense"
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    article_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("budget_expense_article.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)   # схема: gt=0
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True)
    branch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("branch.id", ondelete="SET NULL"), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # без FK (полиморфная)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # индекс (tenant_id, domain, occurred_on) — под агрегацию факта
```

Примечания:
- FK на `company/branch/site` — **настоящие** (новая таблица; wa02-грабли касались только
  `add_column` с FK на существующую таблицу). `ondelete="SET NULL"` — удаление филиала не теряет расход.
- `entity_type/entity_id` — полиморфная ссылка без FK; валидация на API-слое (см. слой 3).
- Точные имена таблиц для FK (`company.id`/`branch.id`/`site.id`) имплементер сверяет с
  `master_data.py` (`__tablename__`).

### Слой 2 — миграция `bg01` (чисто аддитивная)

`backend/app/migrations/versions/20260717_bg01_safety_budget_core.py`:
- `revision = "20260717_bg01_safety_budget_core"`, `down_revision = "20260715_re01_automation_rules"`.
- `upgrade`: `create_table` × 3 (колонки TenantBaseModel + SoftDeleteMixin + свои; индексы:
  `ix_safety_budget_tenant_domain (tenant_id, domain)`, `uq_budget_expense_article_tenant_code
  UNIQUE (tenant_id, code)`, `ix_budget_expense_tenant_domain_occurred (tenant_id, domain,
  occurred_on)`). Порядок: article → budget → expense (FK на article).
- `downgrade`: честный реверс (drop expense → budget → article).
- **Без PG-enum вообще** (VARCHAR) — parity-гейт не затрагивается.
- **Критерий:** PG16-гейт (`scripts/ci/local_gate.py --db-only`) зелёный — round-trip
  upgrade→downgrade→upgrade. SQLite alembic не гоняется (unit-тесты — `metadata.create_all`).

### Слой 3 — модуль `backend/app/modules/budget/` (конвенция rules_engine)

`service.py` — `BudgetService(session, tenant_id)` + typed-исключения
(`BudgetNotFound`, `ArticleNotFound`, `ExpenseNotFound` → 404; `ArticleCodeConflict` → 409
`ARTICLE_CODE_EXISTS`; `BudgetValidationError(code)` → 422 typed-коды):

- CRUD бюджетов (create/list/get/update/soft_delete; allowlist полей на PATCH; повторная проверка
  инварианта периода на merged stored+incoming — прецедент СИЗ).
- CRUD статей + `seed_default_articles()` — идемпотентно по `code` (существующие не трогает,
  недостающие добавляет); дефолтный набор (~10 статей, RU-имена):
  `training_external` «Обучение в УЦ», `training_internal` «Внутреннее обучение»,
  `medical_periodic` «Периодические медосмотры», `medical_psychiatric` «Психиатрические
  освидетельствования», `sout` «Спецоценка условий труда» (универсальная, domain=NULL),
  `events_capa` «Мероприятия по улучшению условий», `ppe_purchase` «Закупка СИЗ» (универсальная),
  `services_external` «Услуги сторонних организаций» (универсальная), `other` «Прочее»
  (универсальная). Точный список финализируется в плане.
- CRUD расходов с фильтрами (`domain`, `article_id`, `date_from/date_to`, `company_id`,
  `branch_id`, `site_id`; `order_by occurred_on desc`; limit/offset + count).
- **Tenant-валидация client-supplied FK на запись** (закрытый класс багов
  `fk-user-refs-need-tenant-check`): `article_id`/`company_id`/`branch_id`/`site_id` — строка
  существует, живая (`deleted_at IS NULL` где применимо) и `tenant_id` совпадает → иначе 422
  `unknown_article`/`unknown_company`/`unknown_branch`/`unknown_site`. Согласованность:
  `article.domain` ∈ {NULL, expense.domain} → иначе 422 `article_domain_mismatch`; `article`
  неактивна → 422 `article_inactive`; `entity_type` соответствует `EXPENSE_ENTITY_TYPES[domain]`
  → иначе 422 `invalid_entity_type`; `entity_id` задан ⇔ задан `entity_type`, строка существует
  в tenant → иначе 422 `unknown_entity`.

`aggregation.py` — чистые вычисления (без N+1, SQL-агрегаты):

```python
@dataclass(slots=True, frozen=True)
class DomainActual:
    actual_total: float
    by_article: list[ArticleActual]     # (article_id | None, article_name | "— без статьи", amount)
    expense_count: int

async def compute_domain_actual(session, tenant_id, domain, period_start, period_end) -> DomainActual
async def compute_overview(session, tenant_id, date_from, date_to) -> BudgetOverview
async def compute_breakdown(session, tenant_id, dimension, date_from, date_to) -> BreakdownResult
```

- `compute_domain_actual`: Σ `amount` по `budget_expense` where tenant, domain,
  `occurred_on ∈ [start, end]` (обе даты — Date, границы включительно; datetime-граблей СИЗ здесь
  нет), `deleted_at IS NULL`; группировка по статье одним `GROUP BY` c outerjoin имени статьи.
- `compute_overview`: 4 домена. Для `training|medical|events`: `planned` = Σ `planned_amount`
  бюджетов, чей период **пересекается** с окном (без пропорции — семантика документируется в
  docstring и схеме), `actual` = Σ расходов в окне, `remaining = planned - actual`, +
  `budgets: [{id, name, period, planned, actual_own_period, remaining}]` (факт каждого бюджета —
  по его собственному периоду). Для `ppe`: план из `ppe_safety_budget` (та же overlap-семантика),
  факт — реюз `app.modules.ppe.budget.compute_budget_actual` (+ его `unpriced_receipt_count`
  прокидывается как предупреждение), `read_only=True` в ответе. Дефолт окна — текущий календарный
  год (`date(today.year, 1, 1)`..`date(today.year, 12, 31)`).
- `compute_breakdown(dimension ∈ {article, domain, company, branch, site})`: факт-разрез журнала
  расходов одним `GROUP BY` per dimension; имена из master-data/справочника; **None-bucket**
  `{"id": "", "name": "— без привязки"}` (для article — «— без статьи») только при ненулевой
  сумме; сортировка `amount desc, name asc`; cap 200 строк (`total` — до капа); unknown dimension
  → `BudgetValidationError("breakdown_dimension_unknown")` → 422; `date_from > date_to` → 422
  `window_invalid` (нейтральный код — общий для overview и breakdown; ревью-решение волны:
  не «breakdown»-имя на /overview). СИЗ-факт в breakdown **не
  входит** (у складского леджера нет измерений компания/филиал/объект — задокументировано в
  docstring и в UI-подписи; follow-up срез-2).

### Слой 4 — схемы `backend/app/schemas/budget.py`

`SafetyBudgetCreate/Update/Read/Page/Detail` (зеркало `PPESafetyBudget*`; `Detail` = Read +
`actual_total`/`remaining`/`by_article`/`expense_count`), `BudgetArticleCreate/Update/Read/Page`,
`BudgetExpenseCreate/Update/Read/Page` (Read включает `article_name`, имена измерений не
денормализуются — фронт берёт из своих справочников), `BudgetOverviewResponse`
(`generated_at`, `date_from/date_to`, `domains: [{domain, read_only, planned, actual, remaining,
warning_unpriced_receipts?, budgets: [...]}]`), `BudgetBreakdownResponse` (зеркало
analytics-breakdown: `dimension`, `total`, `items: [{id, name, amount}]`). Валидаторы: период
(`period_end >= period_start`), `planned_amount ge=0`, `amount gt=0`, `domain` ∈ whitelist,
`min_length=1` на name/title/code.

### Слой 5 — API `backend/app/api/routes/` нет; роутер в модуле `backend/app/modules/budget/api.py`

`APIRouter(prefix="/budget")`, регистрация кортежем в `DOCUMENT_CORE_ROUTER_REGISTRATIONS`
(`route_groups.py`, тег `budget`). **Все эндпоинты за FeatureGate `budget`** (default-off;
`is_feature_enabled(..., default=False)`; 404 `api_problem_detail(code="BUDGET_DISABLED",
message="Budget feature is not enabled for this tenant")` — содержит «is not enabled» для
фронтового `isFeatureDisabledError`). `TenantContextValidator.ensure_tenant_context(tenant)`
первой строкой каждого хендлера (конвенция rules_engine). Audit — явный `_audit()`-хелпер до
commit (конвенция rules_engine). **Статические пути (`/overview`, `/breakdown`, `/articles/*`)
объявлять ДО путей с `{id}`.**

| Метод + путь | Доступ | Ответ |
|---|---|---|
| `GET /budget/overview` | Read | `BudgetOverviewResponse` |
| `GET /budget/breakdown?dimension&date_from&date_to` | Read | `BudgetBreakdownResponse` |
| `POST /budget/budgets` | Write + audit | `SafetyBudgetRead` (201) |
| `GET /budget/budgets` | Read | `SafetyBudgetPage` (фильтр `domain`, ETag+304) |
| `GET /budget/budgets/{budget_id}` | Read | `SafetyBudgetDetail` |
| `PATCH /budget/budgets/{budget_id}` | Write + audit | `SafetyBudgetRead` |
| `DELETE /budget/budgets/{budget_id}` | Write + audit | 204 (soft) |
| `POST /budget/articles` | Write + audit | `BudgetArticleRead` (201; дубль кода → 409) |
| `GET /budget/articles` | Read | `BudgetArticlePage` (ETag+304) |
| `PATCH /budget/articles/{article_id}` | Write + audit | `BudgetArticleRead` |
| `DELETE /budget/articles/{article_id}` | Write + audit | 204 (soft) |
| `POST /budget/articles/seed-defaults` | Write + audit | `{created: int, skipped: int}` |
| `POST /budget/expenses` | Write + audit | `BudgetExpenseRead` (201) |
| `GET /budget/expenses` | Read | `BudgetExpensePage` (фильтры, ETag+304) |
| `PATCH /budget/expenses/{expense_id}` | Write + audit | `BudgetExpenseRead` |
| `DELETE /budget/expenses/{expense_id}` | Write + audit | 204 (soft) |

RBAC: `_BUDGET_READ_ROLES = _BUDGET_WRITE_ROLES = ["admin", "owner", "accountant", "ot_pb_lead"]`
(прецедент CRM-финансов admin/owner/accountant + лид службы ОТ; слаги сверить с `rbac_abac.py` —
`accountant` и `ot_pb_lead` подтверждены грепом). Через `abac(_tenant_resource_id,
required_roles=..., action=...)` — Annotated-депсы Read/Write per-endpoint (конвенция rules_engine).

### Слой 6 — demo-сид

`_seed_budget_demo(session, tenant_db_id)` в `backend/app/services/demo_bootstrap.py` (вызов в
конце `bootstrap_demo_tenant()`, идемпотентно): включить флаг `budget`
(Feature + FeatureEnablement), `seed_default_articles`, 3 бюджета (по одному на домен, период —
текущий год), ~5 расходов с разными статьями/доменами и хотя бы одним `site_id`/`branch_id`
и одной entity-ссылкой (на demo-CAPA), чтобы overview/breakdown в demo были живыми.

### Слой 7 — фронт

- **`frontend/src/api/budget.ts`** — typed `budgetApi` (16 методов), DTO в
  `frontend/src/types/dto/budget.ts`, копия `isFeatureDisabledError` (конвенция).
- **`frontend/src/pages/budget/BudgetPage.tsx`** (default-export, lazy) + vocab
  `budgetVocab.ts` (RU-лейблы доменов/статей/dimension'ов).
- Маршрут+навигация **строго парой** (guard-тест `navigationConfigRoutes`): `pageRegistry.tsx` +
  группа в `routeGroups.tsx` (permission `BUDGET_VIEW`) + NavItem «Бюджет безопасности» в группе
  «Бизнес и аналитика» (`navigationConfig.ts`) + строка скрытия по флагу в `navVisibility.ts`
  (`item.to === "/budget" && featureFlags.budget === false`).
- Права фронта: `PERMISSIONS` + `BUDGET_VIEW`/`BUDGET_MANAGE`; admin/owner — через
  isAdminUser-байпас; `accountant`/`ot_pb_lead` — во фронтовый `ROLE_PERMISSIONS`;
  `ot_pb_head` получает через ALL_PERMISSIONS-механику. Write-контролы под `<Can
  permission={BUDGET_MANAGE}>`.
- Вкладки (Radix Tabs, отдельные компоненты `frontend/src/features/budget/*`):
  1. **Сводка** — период-фильтр (дефолт: текущий год), 4 карточки доменов план/факт/остаток
     (СИЗ — бейдж «ведётся на складе», ссылка на `/warehouse`, предупреждение про N приходов без
     цены), разрез: dimension-toggle статья|домен|компания|филиал|объект + простая HTML-таблица с
     CSS-баром (конвенция ManagementDashboardPage, НЕ recharts/TanStack) + подпись «СИЗ-закупки в
     разрезе не участвуют».
  2. **Бюджеты** — реестр (фильтр по домену) + `BudgetFormDialog` (`{trigger, initialData?,
     onSubmitted?}`); строка → деталь: план/факт/остаток + разбивка по статьям.
  3. **Расходы** — журнал с фильтрами + `ExpenseFormDialog`: домен-селект → статьи фильтруются
     (universal+доменные), дата/сумма/название, селекты компания/филиал/объект (справочники
     `/companies`, `/branches`, `/sites` limit=200; тихая деградация при 403), опциональный блок
     «Связать с записью» (entity_type фиксируется доменом, `entity_id` — текстовый input;
     typeahead — follow-up).
  4. **Статьи** — реестр + `ArticleFormDialog` + кнопка «Заполнить стандартными» (idempotent).
- Feature-off → EmptyState «Функция недоступна» (паттерн RulesPage). Ошибки API — глобальный
  toast, в catch страниц ничего не делать.

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| бюджет/статья/расход не найдены / cross-tenant / soft-deleted | 404 |
| `period_end < period_start` | 422 (валидатор схемы) |
| `planned_amount < 0` / `amount <= 0` | 422 |
| `domain` вне whitelist (бюджет/расход) | 422 `unknown_domain` |
| `article_id`/`company_id`/`branch_id`/`site_id` чужой/несуществующий | 422 `unknown_*` (tenant-валидация) |
| статья другого домена / неактивная | 422 `article_domain_mismatch` / `article_inactive` |
| `entity_type` не соответствует домену / `entity_id` без типа / запись не найдена в tenant | 422 `invalid_entity_type` / `unknown_entity` |
| дубль кода статьи (в т.ч. с soft-deleted тёзкой) | 409 `ARTICLE_CODE_EXISTS` (пин-тест) |
| `dimension` вне whitelist / `date_from > date_to` | 422 `breakdown_dimension_unknown` / `window_invalid` |
| расход без статьи | учитывается в факте; в разрезе по статьям — bucket «— без статьи» |
| нет расходов в периоде | `actual=0`, `remaining=planned` |
| пересекающиеся периоды бюджетов | допускаются; факт бюджета — по его периоду; overview честно суммирует планы пересекающихся с окном |
| СИЗ-приходы без цены в окне overview | `warning_unpriced_receipts` в домене `ppe` (прокинут из `compute_budget_actual`) |
| флаг `budget` ВЫКЛ | 404 на всех `/budget/*`; фронт — EmptyState |
| удаление статьи/филиала/объекта | расходы живут (`SET NULL`), попадают в «— без привязки» |
| складской учёт | НЕ затронут: модуль только ЧИТАЕТ `ppe_safety_budget` и складской леджер |

## Тесты (TDD, слои как у СИЗ-бюджета)

- **Модель/схема:** round-trip 3 таблиц (`metadata.create_all`); unique (tenant, code) статьи;
  валидаторы схем (период/суммы/domain-whitelist).
- **Сервис CRUD:** бюджеты/статьи/расходы — create/list(фильтры+пагинация)/get/update(allowlist)/
  soft-delete; tenant-изоляция (чужой → NotFound); soft-deleted не в списках; seed-defaults
  идемпотентен (второй вызов `created=0`); 409 на дубль кода (и с soft-deleted тёзкой).
- **Tenant-валидация записи расхода:** каждый из `article_id`/`company_id`/`branch_id`/`site_id`/
  `entity_id` чужого tenant'а → 422; `article_domain_mismatch`; `invalid_entity_type`;
  валидная entity-ссылка на CAPA/сессию/медосмотр — проходит.
- **Агрегация:** `compute_domain_actual` — суммирование в границах (включительно), чужие
  домены/даты/soft-deleted не считаются, разбивка по статьям + «— без статьи»;
  `compute_overview` — overlap-семантика планов, факт per-бюджет по его периоду, **СИЗ-домен:
  план из `ppe_safety_budget` + факт из складского леджера + unpriced-warning** (интеграционный
  тест с реальными движениями склада); `compute_breakdown` — все 5 dimension'ов, None-bucket,
  cap, сортировка, 422-коды.
- **API:** happy-path всех 16 роутов; flag-off→404; RBAC-матрица (accountant/ot_pb_lead — да;
  ot_specialist/worker — 403); ETag/304 на списках; статические пути не съедаются `{id}`-роутами.
- **Фронт:** vitest BudgetPage — 4 вкладки, overview-рендер (вкл. СИЗ-строку read-only),
  создание бюджета/расхода/статьи через диалоги (моки budgetApi), feature-off EmptyState,
  guard-тест навигации проходит; `tsc` 0; `vite build` 0.
- **Гейты:** ruff/black; **OpenAPI baseline пере-снять** (+16 роутов `/budget/*` + схемы;
  `--compare` зелёный, ARCH-4); **PG16-гейт** round-trip `bg01`; полный vitest; живая верификация
  dev_lite (сид → `/budget` 200 → создать расход через UI → overview обновился).

## Явно ВНЕ объёма (срез-2 / follow-up)

- **Заявки на возмещение СФР** (workflow черновик→подана→одобрена/отклонена→выплачена; связь с
  расходами) — срез-2.
- Измерения (branch/site) у СИЗ-факта; вход СИЗ в breakdown — требует связки склад→филиал.
- Бюджеты с привязкой к филиалу/компании (сейчас tenant-wide — прецедент СИЗ); пропорция планов
  при частичном пересечении окна.
- Автосбор факта из доменов (генерация расхода при завершении обучения/медосмотра по прайсу).
- Typeahead для entity-ссылок и справочников; экспорт в report-builder (5-й датасет); графики.
- Мультивалюта (одна валюта, без поля `currency` — прецедент СИЗ).

## Self-Review

- **Placeholder scan:** TBD нет; дефолтный список статей помечен «финализируется в плане» —
  осознанная передача в writing-plans, не дыра.
- **Внутренняя согласованность:** 3 модели ↔ схемы ↔ сервис ↔ 16 роутов ↔ 4 вкладки согласованы;
  инвариант «план персистентен / факт вычисляем» один и тот же в §Цель, слоях 3 и в тестах;
  СИЗ read-only описан одинаково в решении 3, слое 3 (overview) и edge-cases.
- **Скоуп:** один срез = 1 аддитивная миграция + 3 модели + модуль (service/aggregation/api/
  schemas) + сид + страница с 4 вкладками; ~11-13 TDD-задач — сопоставимо с rules-engine срез-1.
- **Неоднозначности сняты:** overlap-семантика планов в overview (без пропорции, документируется);
  СИЗ не в breakdown (подпись в UI); article nullable → «— без статьи»; entity-ссылка опциональна
  и валидируется по домену; RBAC-роли названы поимённо.
- **Адверсариальные линзы:** tenant-валидация ВСЕХ client-supplied FK (класс багов #749-751);
  полиморфная entity-ссылка без FK — но с whitelist+existence-проверкой; None-bucket не теряет
  деньги молча; cap 200 с честным total; статические пути до `{id}`; unique статьи ловит
  IntegrityError→409 (гонка); деньги Numeric(14,2); breakdown без N+1 (GROUP BY).

## Анти-грабли (операционка из прошлых волн)

- Миграция: `bg01` от `re01` (единственный head — проверено); **postgresql.ENUM не нужен**
  (VARCHAR-only) — parity-гейт не трогаем; честный downgrade; PG16 round-trip обязателен.
- OpenAPI baseline: пере-снять снапшот (`check_openapi_snapshot.py --snapshot`), standalone-запуск
  требует `PYTHONPATH=backend` + `SECRET_KEY`/`S3_*` env; зафиксировать счётчики в handoff.
- Backend pytest: PowerShell, батчи ≤4-5 файлов, timeout 600000мс ОДИН раз (холодный импорт
  минуты), при зависании — `-p magic_stub` (памятка windows-pytest-magic-import-hang); вывод в
  лог-файл + `EXIT=$LASTEXITCODE`.
- Фронт: worktree без node_modules → `npm ci --prefer-offline` один раз; полный vitest не
  параллелить с другими задачами, красный прогон перепроверять изолированно; nav+route парой
  (guard-тест); loader в `useCallback` (иначе бесконечный цикл useAsyncResource).
- dev_lite сам ставит `DEMO_BOOTSTRAP=0` → сидить `scripts/bootstrap_demo_tenant.py --force`
  (c `DATABASE_URL=sqlite+aiosqlite:///./dev.db` + `SECRET_KEY`/`S3_*`).
- Git: работа в изолированном worktree `tz-continuation-d43adc`, атомарные коммиты
  `git commit -- <paths>`, push после каждой задачи (git-multisession-hazard).
- Публичный репо: PR-body минимальный, без инвентаризации дыр (политика disclosure).
