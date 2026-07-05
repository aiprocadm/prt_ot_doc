# P10-06 СИЗ склад — срез «Бюджет безопасности (СИЗ: план vs факт закупок)» — Design

**Дата:** 2026-07-05
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`; ТЗ `vNext §12.4` «Бюджетный контур», `TZ_FULL_UNIFIED.md:369` `[v1.1]`)
**Предшественники (влиты в main):** журнал движений (`PPEStockMovement`, `wa04`, FIFO) → мин-остаток/дефицит (`wa05`) → инвентаризация (`wa06`) → перемещения (`wa07`) → поставщики (`PPESupplier`, `wa08`, `/stock/reorder`, PR #725). Параллельно (НЕ влита, PR #726): мобильная выдача (чисто фронт, без миграции).
**Driver:** brainstorming → writing-plans → subagent-driven-development.
**Head-миграция на старте:** `20260704_wa08_ppe_supplier` (единственный head, в main). Новая миграция `wa09` чейнится от неё.
**База ветки:** `main`@`d4f1375c` (новая ветка `feat/p10-06-ppe-safety-budget`; `wa09` от `wa08` — обе в main). Независимый PR (не стек на мобильной выдаче).

## Цель

Дать складу СИЗ **бюджетный контур план↔факт по закупкам СИЗ** поверх честного остатка, не трогая
инвариант «`batch.quantity` меняется только проводкой». Менеджер задаёт **план** расходов на СИЗ за
период, система считает **факт** (что реально потрачено на закупку СИЗ за период) и остаток бюджета —
с разбивкой факта по категориям СИЗ.

**Осознанное сужение объёма (brainstorming):** ТЗ §12.4 «Бюджет безопасности» — **кросс-доменный** контур
(СИЗ + обучение + медосмотры + мероприятия + статьи расходов + заявки на возмещение + аналитика по
филиалам). Это отдельный мульти-срезовый под-проект. Этот срез = **только СИЗ-часть в рамках P10-06**;
остальное — follow-up (см. «Вне объёма»).

## Принятые решения (brainstorming, 2026-07-05, AskUserQuestion)

1. **Объём = только бюджет СИЗ** (P10-06), не полный §12.4. Кросс-домен (обучение/медосмотры/мероприятия,
   статьи расходов, заявки на возмещение, кросс-доменная аналитика) — отдельный под-проект.
2. **Факт = закупочные расходы (procurement spend):** Σ по приходным проводкам (`kind="receipt"`,
   `quantity_delta>0`, `occurred_at ∈ [период]`) от `quantity_delta × batch.unit_cost`. (Отклонён
   «consumption spend» — стоимость выданного работникам, аллокация по подразделениям; отклонён «оба» —
   больше объём. Consumption — follow-up.)
3. **Источник цены = `PPEStockBatch.unit_cost`** (цена за единицу лота, nullable, аддитивно). (Отклонён
   cost-на-проводке — money-поле в append-only журнал + каждый приходный путь обязан его давать; отклонён
   standard-cost на позиции — это план, не факт.)
4. **Гранулярность бюджета = период (диапазон дат) + tenant-wide,** одна плановая сумма; отчёт показывает
   **разбивку факта по категориям СИЗ** (`item.category`) для инсайта. (Отклонён per-category бюджет —
   больше модель; отклонён per-branch — приход НЕ атрибутируется к филиалу сегодня, партия не связана с
   `Branch`; нужна связка batch→branch — follow-up.)
5. **Факт — вычисляемый агрегат, НЕ персистентная сумма** (зеркало `compute_shortages`/`build_reorder_draft`):
   единственный источник истины — журнал движений; сумма считается по запросу.
6. **Инвариант честного остатка не трогается:** `unit_cost` — метаданные; `_write_movement`/`Σdelta` не
   меняются. Обязательный якорь: существующие остаток-тесты зелёные.

## Архитектура

### Слой 1 — модель `backend/app/models/ppe.py` (новая сущность + 1 nullable-колонка, аддитивно)

**Новая `PPESafetyBudget`** (рядом с master-data СИЗ):

```python
class PPESafetyBudget(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ppe_safety_budget"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    planned_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

**Цена лота — `PPEStockBatch.unit_cost`** (nullable, деньги — `Numeric(14,2)` typed `float`, как
`finance.py`/`tenant_billing.py`):

```python
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
```

- Индекс на `tenant_id` по образцу соседних таблиц. `period_*` без спец-констрейнтов (пересечения периодов
  допускаем — YAGNI). Денежные поля — `Numeric`, НЕ float-колонка (точность).

### Слой 2 — миграция `wa09` (чисто аддитивная)

`backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py`:
- `revision = "20260705_wa09_ppe_safety_budget"`, `down_revision = "20260704_wa08_ppe_supplier"`.
- `upgrade`: `op.create_table("ppe_safety_budget", ...)` (колонки `TenantBaseModel` + `SoftDeleteMixin` +
  `name`/`period_start`/`period_end`/`planned_amount`/`notes`; индекс `tenant_id`) +
  `op.add_column("ppe_stock_batch", sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True))`.
- `downgrade`: реверс — `drop_column("ppe_stock_batch","unit_cost")` затем `drop_table("ppe_safety_budget")`.
  Честный (не `pass`).
- **Критерий:** PG16-гейт (`scripts/ci/local_gate.py --db-only`) зелёный — round-trip
  upgrade→downgrade→upgrade; чисто аддитивно, enum/backfill нет. Alembic на SQLite не гоняется
  (initial_schema JSONB) — unit-тесты строят схему через `metadata.create_all`.

### Слой 3 — сервис `backend/app/modules/ppe/budget.py` (новый модуль)

CRUD (зеркало `suppliers.py`) + вычисление факта:

```python
async def create_budget(session, *, tenant_id, name, period_start, period_end,
                        planned_amount, notes=None) -> PPESafetyBudget
async def list_budgets(session, tenant_id, *, limit, offset) -> tuple[list[PPESafetyBudget], int]
async def get_budget(session, tenant_id, budget_id) -> PPESafetyBudget   # None → BudgetNotFound
async def update_budget(session, tenant_id, budget_id, **fields) -> PPESafetyBudget  # allowlist
async def soft_delete_budget(session, tenant_id, budget_id) -> None
```

- `BudgetNotFound(Exception)` → роут 404 (как `SupplierNotFound`).
- `list_budgets` tenant-scoped, `deleted_at IS NULL`, `order_by(period_start.desc())`, `limit/offset` + count.

**Вычисление факта — чистый агрегат `compute_budget_actual`** (батч-запросы, без N+1):

```python
@dataclass(slots=True, frozen=True)
class BudgetCategoryActual:
    category: str
    amount: float

@dataclass(slots=True, frozen=True)
class BudgetActual:
    actual_total: float
    by_category: list[BudgetCategoryActual]
    priced_receipt_count: int
    unpriced_receipt_count: int

async def compute_budget_actual(session, tenant_id, period_start, period_end) -> BudgetActual
```

- Источник — приходные проводки: `select(PPEStockMovement)` where `tenant_id`, `kind == "receipt"`,
  `quantity_delta > 0`, `occurred_at` в `[period_start, period_end]` (границы включительно; `occurred_at`
  — datetime, период — даты: `period_end` берём по конец дня). Джойн к партии (`batch_id`) за `unit_cost`
  и к позиции (`item_id`) за `category` — **один запрос с join**, не lazy per-movement.
- `actual_total = Σ(quantity_delta × batch.unit_cost)` по проводкам, где `unit_cost IS NOT NULL`.
- `by_category` — та же сумма, сгруппированная по `item.category` (пустая категория → `"—"`/`uncategorized`),
  сортировка по `amount desc`.
- **Приходы без цены** (`unit_cost IS NULL`) — **исключаются из суммы, но считаются** (`unpriced_receipt_count`),
  чтобы отчёт честно предупредил «факт неполный: N приходов без цены». `priced_receipt_count` — сколько учтено.
- Проводки на soft-deleted партии/позиции — трактуются как нет данных (join отфильтрует; не воскрешать).

### Слой 4 — схемы `backend/app/schemas/ppe.py` (база `BaseSchema`, ORM-mode)

```python
class PPESafetyBudgetCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    period_start: date
    period_end: date
    planned_amount: float = Field(ge=0)
    notes: str | None = None
    # валидатор: period_end >= period_start (иначе 422)

class PPESafetyBudgetUpdate(BaseSchema):   # partial, exclude_unset; те же границы/ge=0
    name: str | None = Field(default=None, min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    planned_amount: float | None = Field(default=None, ge=0)
    notes: str | None = None

class PPESafetyBudgetRead(BaseSchema):
    id: str
    name: str
    period_start: date
    period_end: date
    planned_amount: float
    notes: str | None

class PPESafetyBudgetPage(BaseSchema):
    items: list[PPESafetyBudgetRead]
    total: int

class PPEBudgetCategoryActualRead(BaseSchema):
    category: str
    amount: float

class PPESafetyBudgetDetail(PPESafetyBudgetRead):   # план + вычисленный факт
    actual_total: float
    remaining: float          # planned_amount - actual_total (может быть отрицательным = перерасход)
    by_category: list[PPEBudgetCategoryActualRead]
    priced_receipt_count: int
    unpriced_receipt_count: int
```

Расширение существующих (аддитивно, nullable): `PPEStockBatchCreate` / `PPEStockBatchUpdate` /
`PPEStockBatchRead` — `+ unit_cost: float | None` (Field `ge=0` где применимо).

### Слой 5 — API `backend/app/api/routes/ppe.py` (за `WarehouseFeatureGate`)

| Метод + путь | Доступ | Аудит | Ответ |
|---|---|---|---|
| `POST /budgets` | `EditorAccess` | `@audit_operation("create","ppe_safety_budget")` | `PPESafetyBudgetRead` (201) |
| `GET /budgets` | `ManagerAccess` | — | `PPESafetyBudgetPage` (`limit`/`offset`, ETag+304 — паттерн `list_items`) |
| `GET /budgets/{id}` | `ManagerAccess` | — | `PPESafetyBudgetDetail` (план + факт/остаток/разбивка/unpriced); нет/cross-tenant→404 |
| `PATCH /budgets/{id}` | `EditorAccess` | `@audit_operation("update","ppe_safety_budget")` | `PPESafetyBudgetRead` |
| `DELETE /budgets/{id}` | `EditorAccess` | `@audit_operation("delete","ppe_safety_budget")` | 204 (soft-delete) |

- Маппинг ошибок: `BudgetNotFound`→404; `period_end<period_start`/`planned_amount<0`/`unit_cost<0`→422 (схема).
- `require_warehouse_feature` (404 когда флаг выкл) на всех.
- Провенанс цены: `create_stock_batch` / `update_stock_batch` принимают/пишут `unit_cost` (валидация `ge=0`);
  `PPEStockBatchRead` возвращает `unit_cost`. `GET /budgets/{id}` зовёт `compute_budget_actual(...,
  budget.period_start, budget.period_end)`.

### Слой 6 — фронт `frontend/src/pages/warehouse/WarehousePage.tsx` + `api/warehouse.ts`

- `warehouseApi` + DTO: `listBudgets/createBudget/updateBudget/deleteBudget/getBudget`
  (`BudgetDto`, `BudgetCreateDto`, `BudgetDetailDto`); расширить `StockBatchDto`(+`unit_cost`),
  `CreateBatchInput`/форму приёмки (+ поле `unit_cost`).
- Секция **«Бюджет безопасности»**: список бюджетов (период, план, факт, остаток, % использовано) + форма
  создания/редактирования (name / период / плановая сумма / заметки) + soft-delete. Открытие бюджета →
  деталь: разбивка факта по категориям + **предупреждение «N приходов без цены»** когда
  `unpriced_receipt_count>0`. Поле «Цена за единицу» в карточке «Новая партия (приёмка)».
- Ошибки submit — в баннере (shared error-state, как в прошлых срезах).
- **Пре-существующий фикс (на этой ветке от main):** `OpsPages.test.tsx` мокает warehouse только
  `listLevels`/`listBatches`, а `WarehousePage` грузит на маунте movements/shortages/counts/transfers/
  levels-by-location/suppliers/reorder (+ теперь `listBudgets`) → зеркалировать полный мок из
  `WarehousePage.test.tsx` + добавить `listBudgets`. (Тот же фикс есть в PR #726; при мерже — superset.)

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| бюджет не найден / cross-tenant / soft-deleted | `404` (`BudgetNotFound`; фича невидима, не 403) |
| `period_end < period_start` | `422` (валидатор схемы) |
| `planned_amount < 0` / `unit_cost < 0` | `422` (`ge=0`) |
| пустое `name` | `422` (`min_length=1`) |
| приход без `unit_cost` в периоде | исключён из `actual_total`, учтён в `unpriced_receipt_count` (честная неполнота) |
| нет приходов в периоде | `actual_total=0`, `by_category=[]`, `remaining=planned_amount` |
| позиция без категории | группа `"—"` (uncategorized) в разбивке |
| пересекающиеся периоды бюджетов | допускаются; факт считается по периоду конкретного бюджета |
| флаг `warehouse` ВЫКЛ | `404` на `/budgets*` |
| остаток честного баланса | НЕ затронут: `unit_cost` — метаданные; факт — вычисляемый агрегат; `Σdelta`/`_write_movement` не меняются (якорь `before==after`) |

## Тесты (TDD)

- **Модель/схема:** `PPESafetyBudget` round-trip (`metadata.create_all`); `PPESafetyBudgetRead`/`Detail`
  `model_validate`; `PPEStockBatchRead` отдаёт `unit_cost`.
- **Миграция `wa09`:** upgrade создаёт таблицу + колонку; downgrade реверсит; round-trip только на PG16-гейте.
- **Сервис CRUD:** create/list(пагинация+порядок)/get/update(allowlist)/soft-delete; tenant-iso (чужой →
  `BudgetNotFound`); soft-deleted не в списке.
- **`compute_budget_actual` (юнит + сервис):** приходы в периоде суммируются (`delta × unit_cost`); вне
  периода — не учитываются; `unit_cost IS NULL` — исключён из суммы, учтён в `unpriced_receipt_count`;
  разбивка по категориям корректна (в т.ч. uncategorized); не-receipt проводки (issue/writeoff/transfer/
  adjustment) НЕ считаются; **инвариант остатка** не затронут (`on_hand` до/после — как было).
- **API:** `POST/GET/PATCH/DELETE /budgets`; `GET /budgets/{id}` форма ответа (plan/actual/remaining/
  by_category/unpriced) + сценарий с приходами; batch `unit_cost` create/read; `period_end<start`→422;
  `planned_amount<0`→422; flag-off→404; cross-tenant→404; RBAC (Manager read / Editor write).
- **Фронт:** vitest WarehousePage — секция бюджета (CRUD + деталь с разбивкой + unpriced-warning), поле
  `unit_cost` в форме приёмки; `tsc` 0, `vite build` 0; OpsPages-мок обновлён (полный + `listBudgets`).
- **Гейты:** ruff/black; **OpenAPI baseline** пере-снят (`check_openapi_snapshot.py --snapshot`): +5 роутов
  budgets + ~5 схем + поле `unit_cost` в batch — чистый additive, `--compare` зелёный; Celery guard без
  изменений (ARCH-4). Зафиксировать счётчики роутов/схем в handoff.

## Явно ВНЕ объёма (следующие срезы / follow-up)

- **Кросс-доменный §12.4:** бюджеты обучения/медосмотров/мероприятий; статьи расходов (expense categories);
  заявки на возмещение; кросс-доменная аналитика — отдельный под-проект «бюджетный контур».
- **Аналитика по филиалам/объектам** (§12.4) — нужна связка `batch → branch/site` (сейчас у партии только
  `location`-строка); отдельный срез.
- **Consumption/issuance-cost** (стоимость выданного, аллокация по подразделениям/работникам).
- Per-category **бюджеты** (сейчас бюджет tenant-wide, разбивка факта — только в отчёте).
- Мультивалюта (сейчас одна валюта, без поля `currency`); standard/planned cost на позиции.
- Cost-на-проводке (варьирующаяся цена доп-приходов в один лот) — сейчас цена на партии.

## Self-Review

- **Placeholder scan:** без TBD/TODO; слои/сигнатуры/схемы/поля конкретны.
- **Внутренняя согласованность:** `PPESafetyBudget`(name/period_start/period_end/planned_amount/notes),
  `unit_cost` на партии, DTO `PPESafetyBudget{Create,Update,Read,Page,Detail}` + `BudgetActual`-датаклассы,
  их схемы, `compute_budget_actual` — согласованы во всех слоях. Факт (procurement) описан один раз.
- **Скоуп:** один срез = аддитивная `wa09` + `PPESafetyBudget` + nullable `unit_cost` + модуль `budget.py`
  (CRUD + `compute_budget_actual`) + 5 роутов + правки batch-схем/роутов + фронт-секция + OpsPages-фикс;
  ~12–14 TDD-задач.
- **Неоднозначности сняты:** факт = procurement (не consumption); цена на партии (не на проводке/позиции);
  бюджет tenant-wide + период-диапазон (не per-category/per-branch); факт — вычисляемый (не персистентный);
  unpriced-приходы исключаются+считаются; §12.4 кросс-домен — вне объёма.
- **Адверсариальные линзы:** инвариант остатка не тронут (unit_cost — метаданные, якорь `before==after`);
  факт без N+1 (один join-запрос проводки↔партия↔позиция); только `kind="receipt"` (не issue/writeoff/
  transfer/adjustment — иначе двойной/ложный учёт); границы периода включительно с концом дня для datetime
  `occurred_at`; unpriced не молчаливо=0 (считается и предупреждается); soft-deleted партия/позиция не
  воскрешает; `Numeric` для денег (не float-колонка); дубль по имени бюджета НЕ уникален (несколько
  бюджетов на период допустимы) — осознанно.

## Анти-грабли

- **Инвариант остатка:** `unit_cost` — только метаданные; `_write_movement`/`record_movement`/`Σdelta` не
  трогать; факт — вычисляемый, не персистить сумму. Якорь-тест `on_hand` до/после приходов/переносов.
- **Только `kind="receipt"` и `quantity_delta>0`** в факте — issue/writeoff/adjustment/transfer в
  procurement-бюджет НЕ входят (transfer вообще Σ=0). Легко ошибиться — покрыть тестом каждый kind.
- **Границы периода:** `occurred_at` — datetime, период — даты; `period_end` включать по конец дня
  (`< period_end + 1 day` или `<= end_of_day`), иначе приходы в последний день периода теряются.
- **Unpriced-приходы:** исключать из суммы, но СЧИТАТЬ и возвращать `unpriced_receipt_count` — иначе факт
  молча занижен и выглядит полным.
- **Деньги — `Numeric(14,2)`**, ORM-тип `float` (как `finance.py`/`tenant_billing.py`); не `Float`-колонка.
- **Факт без N+1:** один запрос с join движение↔партия↔позиция + агрегация в Python (или SQL group-by), не
  lazy `movement.batch`/`movement.item` в цикле.
- **Миграция `wa09`** чейнится от `wa08` (единственный head); чисто аддитивная; честный downgrade;
  PG16-gate round-trip; SQLite alembic не гоняется.
- **OpenAPI baseline пере-снять** (`--snapshot`): новые роуты `POST/GET /ppe/budgets`,
  `GET/PATCH/DELETE /ppe/budgets/{id}` + batch `unit_cost`. Зафиксировать счётчики в handoff, иначе ARCH-4
  красный. Скрипт требует `$env:PYTHONPATH="backend"`.
- **OpsPages.test.tsx** на этой ветке (от main) — pre-existing stale warehouse-мок; обновить до полного +
  `listBudgets` (иначе полный vitest красный; тот же фикс в PR #726 — superset при мерже).
- **Операционка (из прошлых handoff):** worktree без `.venv`/`node_modules` (node_modules стоит с прошлого
  среза, gitignored — пережил branch switch); бэкенд-тесты глобальным `Python313\python.exe -m pytest`
  **батчами ≤4 файлов, через PowerShell** (Git-Bash сегфолтит), таймаут 600000мс ОДИН раз (холодный импорт
  ~2-3 мин); фронт — `npx vitest run <file>` через Bash; OpenAPI/PG16 — контроллером в фоне.
