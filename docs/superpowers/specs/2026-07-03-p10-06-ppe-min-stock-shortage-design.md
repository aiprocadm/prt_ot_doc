# P10-06 СИЗ склад — срез «Мин-остаток + прогноз дефицита» — Design

**Дата:** 2026-07-03
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники (влиты в main):** W-A skeleton (`PPEStockBatch` + `/ppe/stock/*` за флагом `warehouse`, миграция `wa01`) → срез «Журнал движений склада» (`PPEStockMovement` append-only, миграция `wa04`, FIFO-списание при выдаче, честный `/stock/levels`, фронт-секция «Движения», PR #720).
**Driver:** brainstorming → writing-plans → subagent-driven-development.

## Цель

Поверх **честного баланса** (`batch.quantity` — живой кэш on-hand, меняется только проводкой)
дать складу **упреждающий контроль запаса**:

1. Порог **мин-остатка** `min_stock` на позицию каталога (`PPEItem`).
2. **Дефицит к дозаказу** = `max(0, min_stock − on_hand)`.
3. **Прогноз дефицита**: средняя скорость расхода по issue-движениям за скользящее окно →
   **дней до исчерпания** и **дата пробоя порога**.
4. Список `GET /ppe/stock/shortages` + секция «Дефицит / мин-остаток» на `WarehousePage`.

Всё за пилотным флагом `warehouse`. **Watchlist** — позиции с `min_stock > 0` (порог задан);
позиции без порога в отчёт дефицита не попадают (за ними склад по мин-остатку не следят).

## Принятые решения (brainstorming, 2026-07-03)

1. **Срез = мин-остаток + прогноз дефицита** (первый из «последующих срезов», объявленных
   спекой журнала движений: мин-остаток → инвентаризация → поставщики → перемещения).
2. **Гранулярность порога — на позицию `PPEItem`**, без измерения «размер». Обоснование:
   в текущей модели СИЗ размер **не ведётся** (`PPEItem`/`PPEStockBatch`/`PPEIssue` не имеют
   поля size), on-hand и выдачи — на уровне позиции. Порог на позицию консистентен текущей
   гранулярности; вводить измерение «размер» здесь — за рамками (изобретать сущность, которой нет).
3. **Хранение порога — реальная колонка `ppeitem.min_stock`** (миграция `wa05`), не `metadata_json`.
   Обоснование: по порогу нужно фильтровать/сортировать watchlist в SQL (`min_stock > 0`) и иметь
   типобезопасность. `metadata_json` (безмиграционный вариант) отвергнут как не запрашиваемый в SQL.
4. **Глубина прогноза — порог + скорость расхода.** Средний дневной расход по движениям
   `kind=issue` за скользящее окно (default 90 дней) → `days_to_depletion` + `projected_breach_date`.
   Тренд/сезонность — избыточно для среза (YAGNI), отложены.
5. **Поверхность алертов — эндпоинт `GET /ppe/stock/shortages` + секция на `WarehousePage`**
   (pull-based, самодостаточно, за флагом `warehouse`). Проекция в Command Center и
   email/in-app уведомления при пробое — отложены в следующие срезы.

## Архитектура

### Слой 1 — модель `backend/app/models/ppe.py :: PPEItem`

Добавить одно поле:

| Поле | Тип | Смысл |
|---|---|---|
| `min_stock` | `Integer`, not null, `default=0`, `server_default="0"` | порог мин-остатка позиции; `0` = порог не задан (позиция вне watchlist) |

Без изменений в `PPEStockBatch` / `PPEStockMovement`. Инвариант «остаток меняется только
проводкой» из предыдущего среза сохраняется — этот срез только **читает** on-hand, не мутирует.

### Слой 2 — миграция `wa05` (аддитивная)

`backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py`:
- `upgrade`: `op.add_column("ppeitem", sa.Column("min_stock", sa.Integer(), nullable=False, server_default="0"))`.
  Аддитивна — новая колонка на существующей таблице с `server_default` бэкофиллит все строки
  (`min_stock=0` → watchlist пуст, пока порог не задан явно). Новых таблиц/дропов нет.
- `downgrade`: `op.drop_column("ppeitem", "min_stock")` — честно откатывает.
- Критерий: проходит PG16-гейт (`make gate` / `scripts/ci/local_gate.py`); enum-правило не
  затрагивается (колонка `Integer`, не enum).

### Слой 3 — чистая функция прогноза `backend/app/modules/ppe/stock.py`

Рядом с существующим `allocate_fifo` (паттерн «чистая функция без БД, юнит-тест отдельно от SQL»):

```python
@dataclass(slots=True, frozen=True)
class ShortageProjection:
    below_threshold: bool
    deficit: int
    days_to_depletion: float | None
    days_to_threshold: float | None

def project_shortage(on_hand: int, min_stock: int, avg_daily: float) -> ShortageProjection: ...
```

Правила:
- `below_threshold = min_stock > 0 and on_hand < min_stock`
- `deficit = max(0, min_stock − on_hand)`
- `days_to_depletion = on_hand / avg_daily` при `avg_daily > 0`, иначе `None`
- `days_to_threshold = max(0, on_hand − min_stock) / avg_daily` при `avg_daily > 0`, иначе `None`

`projected_breach_date` вычисляется в сервисе (`today + days_to_threshold`), не в чистой функции
(чистая функция не знает «сегодня» — дата инъектируется вызывающим кодом для детерминизма тестов).

### Слой 4 — сервис агрегации `backend/app/modules/ppe/stock.py`

```python
async def compute_shortages(
    session, tenant_id, *, today, window_days=90, only_below=False
) -> list[ShortageRow]: ...
```

Шаги:
1. Выбрать позиции `PPEItem` с `min_stock > 0` (tenant-scoped, `deleted_at IS NULL`).
2. `on_hand` per item = `func.coalesce(func.sum(PPEStockBatch.quantity), 0)` с `group_by(item_id)`
   (тот же паттерн, что `list_stock_levels`, `ppe.py:974-986`).
3. `avg_daily` per item = `Σ|quantity_delta|` по `PPEStockMovement` где `kind = "issue"`
   и `occurred_at >= today − window_days`, делённое на `window_days`. Приход/списание/корректировка
   в расход **не** входят (только фактическая выдача работникам — истинное потребление).
4. Для каждой позиции — `project_shortage(...)` + `projected_breach_date = today + days_to_threshold`.
5. Сортировка: сперва `below_threshold=True`, затем `days_to_depletion` asc (nulls last).
6. `only_below=True` → вернуть только `below_threshold` строки (для компактного счётчика-бейджа).

`today` инъектируется параметром (детерминизм тестов; в роуте — `date.today()` / UTC now).

### Слой 5 — схемы `backend/app/schemas/ppe.py`

- Расширить существующие `PPEItemCreate` / `PPEItemUpdate` / `PPEItemRead` полем
  `min_stock: int` (create: `Field(default=0, ge=0)`; update: `int | None = Field(default=None, ge=0)`;
  read: `int`).
- Новые (рядом с `PPEStockLevelRead`/`PPEStockLevelPage`):

```python
class PPEStockShortageRead(BaseSchema):
    item_id: str
    item_name: str
    min_stock: int
    on_hand: int
    deficit: int
    below_threshold: bool
    avg_daily_consumption: float
    days_to_depletion: float | None
    projected_breach_date: date | None

class PPEStockShortagePage(BaseSchema):
    items: list[PPEStockShortageRead]
    total: int
    window_days: int
```

### Слой 6 — эндпоинт `backend/app/api/routes/ppe.py`

```
GET /ppe/stock/shortages
  dependencies=[WarehouseFeatureGate]      # тот же gate, что /stock/levels, /stock/movements
  access: ManagerAccess                     # как /stock/levels
  query: window_days: int = Query(90, ge=1, le=365)
         only_below: bool = Query(False)
  → PPEStockShortagePage
```

- `TenantContextValidator.ensure_tenant_context(tenant)` (как соседние эндпоинты).
- **Без ETag** — зеркалит соседний `/stock/levels` (тоже вычисляемый агрегат, ETag не имеет).
  Обоснование: строки дефицита — агрегат поверх `PPEStockBatch.quantity` + `PPEStockMovement`;
  `compute_list_etag` ключует ответ по `(id, updated_at)` строк, но `PPEItem.updated_at` **не
  меняется** при движении склада → ETag отдавал бы устаревший дефицит после прихода/выдачи
  (silent-stale — класс дефектов, от которого ETag-контракт как раз защищает на обычных списках).
  Отчёт пересчитывается на каждый вызов, как `/stock/levels`. (В ppe.py ETag есть только на
  `/items` и `/issues`; ни один `/stock/*` эндпоинт его не использует — зеркалим их.)
- Установка порога — через существующий item CRUD (`min_stock` в create/update payload); отдельного
  эндпоинта не заводим.

### Слой 7 — фронт `frontend/src/pages/warehouse/WarehousePage.tsx`

- Секция **«Дефицит / мин-остаток»**: таблица (позиция · остаток · порог · дефицит · дней до
  исчерпания · дата пробоя) с бейджами тяжести — красный `below_threshold`, янтарный
  `projected_breach_date` в пределах окна, иначе строка скрыта/зелёная. Счётчик `only_below`-позиций
  в заголовке секции.
- API-клиент: `listShortages(params)` + DTO `PPEStockShortageDto` (зеркало backend-схемы).
- Поле `min_stock` в форме создания/редактирования позиции СИЗ (там же, где правятся `PPEItem`).

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| `min_stock = 0` | позиция вне watchlist (порог выключен) |
| `avg_daily = 0` (нет issue-движений в окне) | `days_to_depletion = None`, `below_threshold` считается по on-hand vs порог |
| `on_hand = 0` и порог > 0 | `deficit = min_stock`, `days_to_depletion = 0`, `below_threshold = True` |
| флаг `warehouse` ВЫКЛ | `WarehouseFeatureGate` отдаёт как остальные `/stock/*` (единый контракт gate) |
| `window_days` вне 1..365 | 422 (валидируется `Query(ge=1, le=365)`) |
| позиция без партий, порог > 0 | `on_hand = 0` → дефицит = порог (склад по позиции просто не наполнен) |

## Тесты

- **Чистая функция** `project_shortage` (без БД): выше/равно/ниже порога, `avg_daily=0`,
  `on_hand=0`, граница `on_hand == min_stock`, расчёт `deficit`/`days_*`.
- **Сервис** `compute_shortages`: watchlist-фильтр (`min_stock>0` only), агрегация `on_hand` по
  нескольким партиям, `avg_daily` только по `kind=issue` в окне (исключает receipt/writeoff/
  adjustment и движения вне окна), сортировка по тяжести, `only_below` фильтр, tenant-iso.
- **API**: happy path, flag-off (gate), tenant-iso, `window_days` (default + clamp 422),
  `only_below`, RBAC (`ManagerAccess`).
- **Миграция** `wa05`: колонка появляется, `downgrade` дропает, аддитивность (PG16-гейт).
- **Фронт**: рендер секции дефицита (бейджи тяжести), установка `min_stock` через форму позиции.

## Явно ВНЕ объёма (следующие срезы)

- Проекция дефицита в Command Center / operational dashboard.
- Email/in-app уведомления при пробое порога (trigger на выдаче или Celery-скан).
- Reorder-target / lead-time / автозаявка на закупку.
- Поставщики, перемещения между складами, инвентаризация — отдельные срезы.
- Прогноз с трендом/сезонностью.

## Self-Review

- **Placeholder scan:** без TBD/TODO; все слои и сигнатуры конкретны.
- **Внутренняя согласованность:** сигнатуры `project_shortage(on_hand, min_stock, avg_daily)`,
  `compute_shortages(session, tenant_id, *, today, window_days, only_below)`, DTO
  `PPEStockShortageRead/Page`, поле `min_stock` — одинаковы во всех слоях. `projected_breach_date`
  в DTO, но не в чистой `ShortageProjection` (осознанно — дата инъектируется в сервисе).
- **Скоуп:** один срез = одна миграция + один read-эндпоинт + расширение item CRUD + одна
  фронт-секция; укладывается в один план реализации.
- **Неоднозначности:** «watchlist» явно определён как `min_stock > 0`; «расход» явно = только
  `kind=issue`; окно по умолчанию 90 дней, `today` инъектируется для детерминизма.
