# P10-06 СИЗ склад — срез «Перемещения между локациями (transfer из локации A в B)» — Design

**Дата:** 2026-07-04
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники (влиты в main):** W-A skeleton (`PPEStockBatch` + `/ppe/stock/*` за флагом `warehouse`, `wa01`) → срез «Журнал движений» (`PPEStockMovement` append-only, `wa04`, FIFO-списание при выдаче, честный `/stock/levels`, PR #720) → срез «Мин-остаток + прогноз дефицита» (`ppeitem.min_stock`, `wa05`, `GET /ppe/stock/shortages`, PR #721) → срез «Инвентаризация» (`ppe_inventory_count[_line]`, `wa06`, `adjustment`-проводки, PR #722).
**Driver:** brainstorming → writing-plans → subagent-driven-development.

## Цель

Поверх **честного баланса** (`batch.quantity` — живой кэш on-hand, меняется только проводкой) дать
складу **перемещения запаса между локациями**: переложить `q` единиц из партии в локации A в ту же
партию (тот же `batch_no`, провенанс сохранён) в локации B. Перемещение — **не новый мутатор**
остатка, а **воркфлоу-поставщик пары `transfer`-проводок** через единственный санкционированный мутатор
`_write_movement`: `−q` на партии-источнике и `+q` на партии-приёмнике в одной транзакции. На уровне
позиции сумма дельт = 0 → `/stock/levels` (агрегат по item) не шелохнётся, а **per-location остаток
честно перетекает** A→B. Всё за пилотным флагом `warehouse`.

## Принятые решения (brainstorming, 2026-07-04)

1. **Срез = перемещения между локациями** (из блока «поставщики / перемещения», объявленного спеками
   журнала движений и инвентаризации как отложенный). Строится прямо на журнале: пара проводок нового
   `kind="transfer"` через уже существующий `_write_movement`. (Отклонён параллельный кандидат
   «поставщики» — чистая master-data, самодостаточна, вынесена в следующий срез.)
2. **Локация — свободная строка** (текущая модель: `batch.location: String(255)`,
   `inventory.scope_location: String(255)` — уже строки). НЕ вводим сущность `PPELocation`: это было бы
   отдельным срезом (справочник + миграция строк в FK + CRUD-экраны), ломающим консистентность с
   `scope_location`. Фронт помогает от опечаток `datalist`-подсказкой из уже существующих локаций +
   нормализацией (`trim`). (Отклонён `PPELocation`-entity — scope creep для этого среза.)
3. **Частичный перенос (split партии), гранулярность — единицы.** Переносим любое `q ≤ on_hand`
   источника; приёмник — **find-or-create** партия с тем же `(tenant, item_id, batch_no)` в локации B.
   (Отклонён whole-batch-move — нельзя двигать часть партии, а в реальном складе это норма; отклонён
   отдельный «location-балансный» леджер — дублирует роль `batch.quantity`.)
4. **Перенос атомарный и мгновенный** (один `POST` = валидация + исполнение пары проводок в одной
   транзакции), **без in-transit-состояния**. У инвентаризации две фазы, потому что там нужна фаза
   подсчёта; у переноса её нет — goods-in-transit (ушло из A, ещё не принято в B) — отдельный будущий
   срез. (Отклонён two-phase transfer — YAGNI для этого среза.)
5. **FIFO-выдача остаётся location-agnostic.** Перенос не меняет `deplete_for_issue`: выдача
   по-прежнему списывает по всем партиям позиции (FIFO по `received_at`). Location-scoped выдача — не в
   этом срезе.
6. **Пара проводок связана общим `ref_id`** (сгенерированный `uuid4`), `ref_type="ppe_transfer"`,
   строкой БЕЗ FK (журнал append-only, переживает hard-delete — та же конвенция, что
   `PPEStockMovement.ref_id`/`replaces_issue_id`). Локации A/B выводятся из партий движений (источник =
   отрицательная дельта, приёмник = положительная) — **новых колонок в журнал не добавляем**.
7. **Per-location остаток — отдельный аддитивный роут** `GET /stock/levels/by-location` (группировка по
   `item_id + location`), НЕ мутация формы существующего `GET /stock/levels` (группировка по `item_id`).
   Не ломаем контракт существующего эндпоинта/OpenAPI-baseline.

## Архитектура

### Слой 1 — модель `backend/app/models/ppe.py` (правка уникального ключа партии)

Единственное изменение схемы — **уникальный ключ `PPEStockBatch`** расширяется локацией, чтобы одна и
та же партия (`batch_no`) могла лежать в разных локациях:

- Было: `UniqueConstraint("tenant_id", "item_id", "batch_no", name="uq_ppe_stock_batch_item_no")`.
- Стало: **уникальный `Index`** `uq_ppe_stock_batch_item_no_loc` по `("tenant_id","item_id","batch_no","location")`
  с `postgresql_nulls_not_distinct=True`.
  - **Почему `Index`, а не `UniqueConstraint`:** `postgresql_nulls_not_distinct` надёжно поддержан на
    unique-`Index` (SQLAlchemy 2.0). `location` nullable → в стандартном SQL NULL'ы «различны», и чистое
    расширение ключа позволило бы дублировать legacy-партии с `location IS NULL`. `NULLS NOT DISTINCT`
    (PG15+) трактует `NULL`-локации как равные → дедуп legacy сохранён точно как прежде.
  - **SQLite (unit-тесты через `metadata.create_all`):** dialect-специфичный kwarg игнорируется; SQLite
    строит обычный unique-index (NULL'ы различны). Это НЕ задевает тесты: перенос требует непустых
    локаций, а сидируемые в тестах партии всегда с локацией. Enum-паритет не затрагивается (текстовых
    enum здесь нет).
- Индекс `ix_ppe_stock_batch_item (tenant_id, item_id)` остаётся.

### Слой 2 — миграция `wa07` (drop+add уникального ключа — НЕ чисто аддитивная)

`backend/app/migrations/versions/20260704_wa07_ppe_stock_batch_location_unique.py`:
- `revision = "20260704_wa07_ppe_stock_batch_location_unique"`,
  `down_revision = "20260703_wa06_ppe_inventory_count"` (текущий единственный head — проверено `glob` versions).
- `upgrade`:
  - `op.drop_constraint("uq_ppe_stock_batch_item_no", "ppe_stock_batch", type_="unique")`;
  - `op.create_index("uq_ppe_stock_batch_item_no_loc", "ppe_stock_batch",
    ["tenant_id","item_id","batch_no","location"], unique=True, postgresql_nulls_not_distinct=True)`.
- `downgrade`: `op.drop_index("uq_ppe_stock_batch_item_no_loc", "ppe_stock_batch")` →
  `op.create_unique_constraint("uq_ppe_stock_batch_item_no", "ppe_stock_batch", ["tenant_id","item_id","batch_no"])`.
- **Критерий:** PG16-гейт (`make gate` / `scripts/ci/local_gate.py --db-only`) зелёный — round-trip
  upgrade→downgrade→upgrade без ошибок; `NULLS NOT DISTINCT` применяется только на PG (не задевает SQLite).
- **Анти-грабли (проверить при реализации):** поддерживает ли установленная версия Alembic
  `postgresql_nulls_not_distinct` в `op.create_index`. Если нет — падать назад на
  `op.execute("CREATE UNIQUE INDEX ... NULLS NOT DISTINCT")` сырым DDL (PG-only ветка), downgrade зеркалит.

### Слой 3 — сервис `transfer_stock` (правка `backend/app/modules/ppe/stock.py`, аддитивно)

Новая константа рядом с `KIND_*`: `KIND_TRANSFER = "transfer"`. **Не** входит в `MANUAL_KINDS`
(перенос — не ручное однопартийное движение; идёт только через свой эндпоинт). Ручной
`POST /stock/movements` уже отвергает `transfer` схемой (`_validate_kind` допускает лишь
receipt/writeoff/adjustment — проверено).

```python
@dataclass(slots=True, frozen=True)
class TransferResult:
    ref_id: str
    out_movement: PPEStockMovement   # источник, delta < 0
    in_movement: PPEStockMovement    # приёмник, delta > 0
    source_batch_id: str
    dest_batch_id: str
    from_location: str
    to_location: str
    quantity: int

async def transfer_stock(
    session, *, tenant_id, source_batch_id, to_location, quantity,
    reason=None, occurred_at=None,
) -> TransferResult
```

1. **Загрузить партию-источник** (`_load_batch` — tenant-scoped, `deleted_at IS NULL`) → нет →
   `StockBatchNotFound` (→404).
2. **Гварды (все → `ValueError`, роут маппит в 400; кол-во ≤0 отсечено схемой в 422):**
   - `quantity > 0`;
   - `to_location` после `strip()` непустая;
   - `to_location != source.location` (иначе перенос в ту же локацию — no-op-ошибка);
   - достаточность остатка проверяет `_write_movement` (guard on-hand ≥ 0) → при нехватке
     `InsufficientStockError` (→400). Дублировать явную проверку `quantity ≤ source.quantity` не
     обязательно, но допустимо для раннего сообщения.
3. **Find-or-create приёмник** — партия `(tenant, item_id=source.item_id, batch_no=source.batch_no,
   location=to_location, deleted_at IS NULL)`:
   - есть → мержим (`+q` на неё);
   - нет → создаём `PPEStockBatch(quantity=0, location=to_location)`, **копируя провенанс** из источника
     (`batch_no`, `received_at`, `certificate_no`, `certificate_expires_at`), `flush` для получения `id`.
   - `to_location` нормализуется (`strip`) до сравнения и записи.
4. **Единый `occurred_at`** = `occurred_at or now(tz=utc)` (обе проводки одним временем).
   `transfer_ref = uuid4().hex`.
5. **Две проводки через `_write_movement`** (единственный мутатор `batch.quantity`), в порядке
   источник→приёмник (сначала списываем — guard on-hand ловит нехватку до создания «фантомного» плюса;
   т.к. приёмник создаётся до проводок, при откате транзакции пустая партия не сохранится):
   - источник: `kind=KIND_TRANSFER, delta=-quantity, reason=reason, occurred_at, ref_type="ppe_transfer", ref_id=transfer_ref`;
   - приёмник: `kind=KIND_TRANSFER, delta=+quantity, reason=reason, occurred_at, ref_type="ppe_transfer", ref_id=transfer_ref`.
6. Вернуть `TransferResult`.

**Инвариант:** `transfer_stock` мутирует остаток **только через `_write_movement`** → «`batch.quantity`
только через сервис проводок» держится. На уровне позиции `Σ delta = 0` → `on_hand` позиции неизменен
(тест-якорь).

### Слой 4 — схемы `backend/app/schemas/ppe.py` (рядом со stock-схемами, база `BaseSchema`)

```python
class PPEStockTransferCreate(BaseSchema):
    source_batch_id: str
    to_location: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None

class PPEStockTransferRead(BaseSchema):
    ref_id: str
    item_id: str
    item_name: str
    batch_no: str
    from_location: str | None
    to_location: str
    quantity: int
    source_batch_id: str
    dest_batch_id: str
    out_movement_id: str
    in_movement_id: str
    reason: str | None
    occurred_at: datetime

class PPEStockTransferPage(BaseSchema):
    items: list[PPEStockTransferRead]
    total: int

class PPEStockLevelByLocationRead(BaseSchema):
    item_id: str
    item_name: str
    location: str | None
    quantity: int
    batch_count: int

class PPEStockLevelByLocationPage(BaseSchema):
    items: list[PPEStockLevelByLocationRead]
    total: int
```

`item_name`/`from_location`/`to_location` в `PPEStockTransferRead` собираются в роуте из батч-map/name-map
(паттерн `list_stock_levels`), не хранятся.

### Слой 5 — API `backend/app/api/routes/ppe.py` (3 роута за `WarehouseFeatureGate`)

Все роуты: `dependencies=[WarehouseFeatureGate]` (404 когда флаг выкл),
`TenantContextValidator.ensure_tenant_context(tenant)`.

| Метод + путь | Доступ | Аудит | Ответ |
|---|---|---|---|
| `POST /stock/transfers` | `EditorAccess` | `@audit_operation("create","ppe_stock_transfer")` | `PPEStockTransferRead` (201) |
| `GET /stock/transfers` | `ManagerAccess` | — | `PPEStockTransferPage` (фильтры `item_id?`/`location?`, `limit`/`offset`, ETag+304) |
| `GET /stock/levels/by-location` | `ManagerAccess` | — | `PPEStockLevelByLocationPage` |

- **`POST /stock/transfers`** (зеркало `create_stock_movement`): парсит `PPEStockTransferCreate` в kwargs,
  зовёт `transfer_stock`. Маппинг: `StockBatchNotFound`→404, `InsufficientStockError`/`ValueError`→400
  (`_ppe_bad_request`), `StaleDataError`→409 (`_ppe_conflict` — конкурентная мутация партии-источника
  бампит `version`). `quantity≤0`/пустая `to_location`→422 (схема). Ответ собирается из `TransferResult`
  + name-map позиции.
- **`GET /stock/transfers`** (зеркало `list_stock_movements` + группировка): движения
  `kind="transfer"` (tenant-scoped), **сгруппированные в пары по `ref_id`** — в паре отрицательная
  дельта = источник (её `batch_id`+location = `from`), положительная = приёмник (`to`). Собираем строки
  `PPEStockTransferRead`. Фильтры: `item_id`, `location` (совпадение по `from` **или** `to`). Порядок —
  `occurred_at desc`. Пагинация по **парам** (не по строкам журнала): выбираем упорядоченные `ref_id`
  среди `kind="transfer"`, лимит/оффсет по ним, затем грузим обе проводки каждой пары. ETag по
  собранным строкам + скалярам фильтров (паттерн `list_stock_movements`). `total` = число пар.
- **`GET /stock/levels/by-location`**: агрегат `sum(quantity)`, `count(id)` по
  `group_by(item_id, location)` c `deleted_at IS NULL` (зеркало `list_stock_levels`, +`location` в group_by),
  name-map по `item_id`. Отдаёт по строке на `(item, location)`. Пустые (нулевые) локации допустимы
  (`location IS NULL` для legacy-партий).

### Слой 6 — фронт `frontend/src/pages/warehouse/WarehousePage.tsx` + `api/warehouse.ts`

- `warehouseApi`: `createTransfer(body)`, `listTransfers(params?)`, `listLevelsByLocation()` +
  DTO-зеркала (`StockTransferDto`, `StockTransferCreateDto`, `StockLevelByLocationDto`) в стиле
  существующих `StockMovementDto`/`PPEStockShortageDto`.
- Секция **«Перемещения между локациями»** на `WarehousePage`:
  - форма «Новый перенос»: `source_batch_id` (ввод; picker партий — follow-up, как в срезе движений),
    `to_location` (`<input list=...>` с `datalist` уже существующих локаций из
    `listLevelsByLocation`), `quantity` (`type=number`, min 1), опц. `reason`. Кнопка «Перенести».
  - таблица истории переносов: позиция · `batch_no` · откуда → куда · кол-во · когда.
  - (опц.) компактная сводка per-location остатков из `listLevelsByLocation` рядом с существующей
    секцией «Остатки».
- Ошибка submit показывается в баннере (shared error-state — как в срезе движений; inline-у-формы —
  осознанный follow-up).

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| источник не найден / cross-tenant / soft-deleted | `404` (`StockBatchNotFound`; фича невидима, не 403) |
| `quantity > on_hand` источника | `400` (`InsufficientStockError` от `_write_movement` guard) |
| `to_location` пустая/whitespace | `422` (схема `min_length=1`) / `400` если только пробелы после strip |
| `to_location == source.location` | `400` (перенос в ту же локацию бессмыслен) |
| `quantity ≤ 0` | `422` (схема `gt=0`) |
| приёмник-партия уже есть в локации B | мерж (`+q` на существующую, провенанс её собственный) |
| приёмника нет | создаётся с `quantity=0` + копия провенанса источника |
| перенос полной партии (`q == on_hand`) | источник обнуляется (партия остаётся с `quantity=0`, не удаляется) |
| конкурентный перенос той же партии | `409` (`StaleDataError` от optimistic-lock `version` на источнике/приёмнике) |
| флаг `warehouse` ВЫКЛ | `404` на всех `/stock/transfers*` и `/stock/levels/by-location` |
| откат транзакции (любая ошибка после create приёмника) | пустая партия-приёмник не сохраняется (всё в одной транзакции запроса) |

## Тесты (TDD)

- **Сервис (с сессией, паттерн существующих stock-тестов):**
  - happy-path частичный перенос: источник `−q`, приёмник `+q`, две проводки `kind="transfer"` с общим
    `ref_id`; **`on_hand` позиции до = после** (инвариант-якорь).
  - find-or-create: перенос в новую локацию создаёт партию с копией провенанса; повторный перенос той же
    партии в ту же локацию B **мержит** (не плодит вторую партию — проверка `NULLS NOT DISTINCT`
    не нужна, локации непустые; проверяем именно дедуп по `(item,batch_no,location)`).
  - полный перенос (`q == on_hand`) → источник `0`, приёмник `= q`.
  - нехватка (`q > on_hand`) → `InsufficientStockError`, ничего не записано (батч-квоты не тронуты).
  - `to_location == source.location` / пустая → `ValueError`.
  - tenant-iso: источник другого тенанта → `StockBatchNotFound`.
  - обе проводки одним `occurred_at`; `reason` прокинут в обе.
- **API:** happy-path 201 + форма ответа; `GET /stock/transfers` группирует пары по `ref_id`, фильтры
  `item_id`/`location`, ETag+304, пагинация по парам; `GET /stock/levels/by-location` разбивает по
  `(item,location)`; 404 (нет/cross-tenant/flag-off), 400 (нехватка/та же локация), 422 (`quantity≤0`,
  пустая `to_location`), 409 (конкурентный — при наличии инфраструктуры для гонки в тестах, иначе unit на
  `StaleDataError`-маппинге), RBAC (`ManagerAccess` на read / `EditorAccess` на write).
- **Миграция `wa07`:** upgrade дропает старый unique + создаёт новый unique-index с локацией; downgrade
  зеркалит; round-trip только на PG16-гейте (`local_gate.py --db-only`). Проверка: после upgrade две
  партии одного `batch_no` в разных локациях сосуществуют; две с `location IS NULL` — по-прежнему
  запрещены (`NULLS NOT DISTINCT`).
- **Фронт:** vitest на новые методы `warehouseApi` (createTransfer/listTransfers/listLevelsByLocation) +
  рендер секции (создание переноса, история, datalist локаций); `tsc` 0, `vite build` 0.
- **Гейты:** ruff/black; **OpenAPI baseline** `docs/stabilization/openapi_routes_baseline.json` пере-снят
  (817/660 → +3 роута + ~5 схем, чистый additive, `--compare` зелёный); Celery guard без изменений (ARCH-4).

## Явно ВНЕ объёма (следующие срезы P10-06)

- Поставщики + провенанс партий (следующий по очереди срез).
- Goods-in-transit (двухфазный перенос: ушло из A / принято в B) — отдельное состояние.
- Location-scoped FIFO-выдача (списывать из конкретной локации).
- Сущность-справочник `PPELocation` (name/code/type) вместо свободной строки.
- Picker партий-источников в форме (сейчас — ввод `batch_id`, как в срезе движений).
- Бюджет безопасности; мобильная выдача.
- Проекция переносов в Command Center / уведомления.

## Self-Review

- **Placeholder scan:** без TBD/TODO; все слои, сигнатуры, таблицы конкретны.
- **Внутренняя согласованность:** `transfer_stock`/`TransferResult`, DTO
  `PPEStockTransfer{Create,Read,Page}` + `PPEStockLevelByLocation{Read,Page}`, поля
  `ref_id`/`from_location`/`to_location`/`quantity` — одинаковы во всех слоях. Пара проводок связана
  `ref_id` и в записи (сервис), и в чтении (группировка роута).
- **Скоуп:** один срез = одна миграция (drop+add unique) + аддитивная правка `stock.py` (+`KIND_TRANSFER`,
  +`transfer_stock`) + 3 роута + 5 схем + расширение фронта; укладывается в один план (~11–13 TDD-задач).
- **Неоднозначности сняты:** локация = строка; перенос = частичный split с find-or-create приёмника;
  атомарный без in-transit; FIFO не меняется; per-location — отдельный роут (не мутация `/stock/levels`);
  пара связана `ref_id` (не FK).
- **Адверсариальные линзы вкатаны:** уникальный ключ меняется на `Index`+`NULLS NOT DISTINCT` (не
  ослабляем дедуп legacy-NULL); мутация только через `_write_movement`; `Σdelta=0` инвариант-якорь;
  `KIND_TRANSFER` — VARCHAR, вне `MANUAL_KINDS`, недоступен ручному эндпоинту; `ref_*` строкой без FK;
  приёмник создаётся в транзакции запроса (откат чистит); Alembic-caveat по `nulls_not_distinct` помечен;
  OpenAPI baseline-файл и счётчики названы.

## Анти-грабли

- `KIND_TRANSFER` — VARCHAR, не PG-enum (enum-parity); вне `MANUAL_KINDS`; ручной `/stock/movements` его
  не принимает (схема `_validate_kind`).
- Остаток мутируется **только через `_write_movement`** (чокпоинт цел); `stock.py` правится аддитивно.
- Пара проводок: источник `−q` / приёмник `+q`, **общий `ref_id`** (`uuid4`), `ref_type="ppe_transfer"`,
  строкой БЕЗ FK — журнал append-only, переживает hard-delete.
- На уровне позиции `Σdelta=0` → `on_hand` позиции неизменен (обязательный тест-якорь; иначе перенос
  «печатает» или «сжигает» запас).
- Уникальный ключ партии: `Index` c `postgresql_nulls_not_distinct=True` (не `UniqueConstraint`) — иначе
  `NULLS NOT DISTINCT` не выразить; SQLite kwarg игнорирует (тесты не задевают, локации непустые).
- Миграция `wa07` чейнится от `wa06` (единственный head); **НЕ чисто аддитивная** (drop+add unique) —
  нужен PG16-gate round-trip; проверить поддержку `nulls_not_distinct` в Alembic, иначе сырой DDL.
- Приёмник — **find-or-create** с `deleted_at IS NULL` и tenant-scope; провенанс копируется из источника;
  `to_location` нормализуется (`strip`) до сравнения/записи.
- `to_location == source.location` и пустая локация — явные ошибки (иначе no-op-перенос/фантомная партия).
- `GET /stock/transfers` пагинирует по **парам** (`ref_id`), не по строкам журнала — иначе половина пары
  утекает за границу страницы.
- Per-location — **новый роут** `GET /stock/levels/by-location`; НЕ трогаем форму `GET /stock/levels`
  (иначе ломается OpenAPI-baseline и существующие консюмеры).
- OpenAPI baseline пере-снять `scripts/ci/check_openapi_snapshot.py --snapshot` — обновляет
  **`docs/stabilization/openapi_routes_baseline.json`** (авторитетный baseline, ARCH-4). Новые роуты:
  `POST /api/v1/ppe/stock/transfers`, `GET /api/v1/ppe/stock/transfers`,
  `GET /api/v1/ppe/stock/levels/by-location`. Зафиксировать новые счётчики (817/660 → 820/~665) в handoff —
  иначе ARCH-4 красный.
