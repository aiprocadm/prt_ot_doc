# P10-06 СИЗ склад — срез «Инвентаризация (сверка факт↔система → adjustment-проводки)» — Design

**Дата:** 2026-07-03
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники (влиты в main):** W-A skeleton (`PPEStockBatch` + `/ppe/stock/*` за флагом `warehouse`, миграция `wa01`) → срез «Журнал движений» (`PPEStockMovement` append-only, миграция `wa04`, FIFO-списание при выдаче, честный `/stock/levels`, PR #720) → срез «Мин-остаток + прогноз дефицита» (`ppeitem.min_stock`, миграция `wa05`, `GET /ppe/stock/shortages`, PR #721).
**Driver:** brainstorming → writing-plans → subagent-driven-development.

## Цель

Поверх **честного баланса** (`batch.quantity` — живой кэш on-hand, меняется только проводкой)
дать складу **инвентаризацию**: периодическую сверку физического факта с системным остатком,
которая при расхождении **порождает `adjustment`-проводки** и тем самым замыкает контур «честного
остатка». Инвентаризация — не новый способ мутировать остаток, а **воркфлоу-поставщик
`adjustment`-движений**: единственная точка мутации `batch.quantity` (сервис `record_movement`)
остаётся неизменной, инвариант держится «бесплатно».

Модель — **двухфазная сессия подсчёта**: черновик (`draft`) со снимком партий → ввод факта по
строкам → предпросмотр расхождений → применение (`apply`), которое выпускает проводки и **замораживает**
документ. Всё за пилотным флагом `warehouse`.

## Принятые решения (brainstorming, 2026-07-03)

1. **Срез = инвентаризация** (первый из блока «поставщики / перемещения / инвентаризация»,
   объявленного спекой журнала движений как отложенный). Строится прямо на журнале: `apply`
   переиспользует `record_movement(kind="adjustment")` (set-to-absolute) — write-path уже есть.
2. **Модель — двухфазная сессия подсчёта** (`ppe_inventory_count` header + `ppe_inventory_count_line`),
   статус `draft → applied / cancelled`. (Отклонены: stateless preview+apply — нет аудируемого
   документа, нельзя переоткрыть прошлый срез; one-shot reconcile — нет ревью диффа перед применением.)
3. **Скоуп среза — опциональный фильтр `item_id` и/или `location`** при создании; строки засеваются
   по одной на **активную партию** под фильтр (пустой фильтр = весь склад). Гранулярность строки —
   **партия** (on-hand ведётся по партиям; `adjustment` применяется к конкретной партии). (Отклонены:
   whole-warehouse-only — нереалистично для больших складов; per-item-only — нельзя счёт «по полке».)
4. **Несосчитанные строки при apply — пропускаются.** `counted_qty` nullable: `null` = «не считали»
   (не трогаем), `0` = «не нашли» (реальное списание в ноль). Частичный подсчёт безопасен — нельзя
   случайно списать непройденную полку. (Отклонены: require-all-counted — запрещает частичный срез;
   uncounted=zero — опасный дефолт, молча зануляет реальный остаток.)
5. **Дельта при apply считается от ЖИВОГО `batch.quantity`, не от снимка `system_qty`.** Т.к.
   `record_movement(adjustment)` — set-to-absolute, любая выдача/приход между засевом и apply
   самокорректируется: итог = сосчитанному. `system_qty` — справочно (что было на старте среза). Это
   намеренное решение против silent-stale (то же основание, что у shortage-эндпоинта без ETag).
6. **`apply`/`cancel` — отдельные action-роуты** (`POST .../apply`, `POST .../cancel`), не общий
   `PATCH status`: доменные переходы несут побочные эффекты (проводки, заморозка) и не дают клиенту
   прыгнуть в `applied` в обход движка.

## Архитектура

### Слой 1 — модели `backend/app/models/ppe.py`

**`PPEInventoryCount(TenantBaseModel, SoftDeleteMixin)`** — заголовок/сессия среза
(`__tablename__ = "ppe_inventory_count"`):

| Поле | Тип | Смысл |
|---|---|---|
| `status` | `String(16)`, not null, default `"draft"` | `draft` / `applied` / `cancelled` — **VARCHAR, не PG-enum** (конвенция enum-parity репо); `default` без `server_default` — новая таблица, бэкофилл не нужен, значение ставит ORM-default (как status в `work_permit`) |
| `scope_item_id` | `ForeignKey("ppeitem.id", ondelete="SET NULL")`, nullable, index | фильтр при засеве (null = все позиции) |
| `scope_location` | `String(255)`, nullable | фильтр при засеве (null = все локации) |
| `note` | `String(255)`, nullable | текстовая метка |
| `applied_at` | `DateTime(timezone=True)`, nullable | ставится при `apply` |

Коллекция строк объявляется **на родителе** со строковым `backref` (house-style `ppe.py` — как
`PPEIssue.relationship(backref=...)`, **не** `back_populates`), каскад delete-orphan на «одной» стороне:
`lines: Mapped[list["PPEInventoryCountLine"]] = relationship("PPEInventoryCountLine", backref="count", cascade="all, delete-orphan")`.
Дочерняя `.count` приходит через backref (отдельно объявлять не нужно).

**`PPEInventoryCountLine(TenantBaseModel)`** — по строке на партию, попавшую в срез
(`__tablename__ = "ppe_inventory_count_line"`; **без** `SoftDeleteMixin` — суб-строка, живёт/умирает с заголовком):

| Поле | Тип | Смысл |
|---|---|---|
| `count_id` | `ForeignKey("ppe_inventory_count.id", ondelete="CASCADE")`, not null, index | родительский срез |
| `item_id` | `ForeignKey("ppeitem.id", ondelete="CASCADE")`, not null | денормализация для отображения/фильтра |
| `batch_id` | `ForeignKey("ppe_stock_batch.id", ondelete="CASCADE")`, not null, index | считаемая партия |
| `system_qty` | `Integer`, not null | снимок `batch.quantity` **на момент засева** (справочно) |
| `counted_qty` | `Integer`, **nullable** | физфакт; `null` = не считали, `0` = «не нашли» |
| `adjustment_movement_id` | `String(36)`, nullable | id `adjustment`-проводки, выпущенной при apply (связь строка→журнал; строкой, БЕЗ FK — журнал append-only и переживёт hard-delete) |

**Без** объявленного `batch`-relationship на строке: чтобы деталь не подтянула soft-deleted партию
ленивым `line.batch` (утечка удалённых данных) и не породила N+1, read-path грузит партии/имена
**явными батч-запросами** с фильтром `deleted_at IS NULL` (см. Слой 6), а `apply` берёт партию через
`record_movement` (который сам фильтрует `deleted_at IS NULL`). `.count` — через backref заголовка.

Индексы: `ix_ppe_inventory_count_line_count (tenant_id, count_id)`, `ix_ppe_inventory_count_line_batch (tenant_id, batch_id)`.
Ограничение: `UniqueConstraint("tenant_id", "count_id", "batch_id", name="uq_ppe_inv_count_line_batch")` — одна строка на партию в срезе.

### Слой 2 — миграция `wa06` (аддитивная)

`backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py`:
- `revision = "20260703_wa06_ppe_inventory_count"`, `down_revision = "20260703_wa05_ppeitem_min_stock"`
  (текущий единственный head; проверено `git`/versions).
- `upgrade`: `op.create_table("ppe_inventory_count", ...)` затем `op.create_table("ppe_inventory_count_line", ...)`
  (+ индексы, + unique). Аддитивно: только новые таблицы, ни колонок в существующих, ни дропов,
  бэкофилл не нужен.
- `downgrade`: `op.drop_table("ppe_inventory_count_line")` затем `op.drop_table("ppe_inventory_count")`
  (строки перед заголовком — FK-порядок).
- Критерий: PG16-гейт (`make gate` / `scripts/ci/local_gate.py --db-only`) зелёный; `status` — VARCHAR,
  enum-правило не затрагивается; SQLite цепочку alembic исторически не тянет (валидирует только PG16).

### Слой 3 — сервис `backend/app/modules/ppe/inventory.py` (НОВЫЙ модуль)

Отдельно от `stock.py`: `stock.py` — движок журнала (проводки/FIFO); `inventory.py` — воркфлоу поверх него.
Исключения (наследуют паттерн `stock.py`): `InventoryCountNotFound`, `InventoryCountNotDraft`.

```python
async def create_count(session, tenant_id, *, scope_item_id=None, scope_location=None, note=None) -> PPEInventoryCount
```
- Валидирует `scope_item_id` (tenant-scoped, если задан → 404 при отсутствии).
- Засевает по строке на **активную** партию (`deleted_at IS NULL`, tenant-scoped) под фильтр
  (`item_id == scope_item_id` если задан; `location == scope_location` если задан),
  `system_qty = batch.quantity` на момент засева. Пустой матч → заголовок с нулём строк (валиден).
- Возвращает созданный `PPEInventoryCount` (status `draft`) со строками.

```python
async def set_line_counts(session, tenant_id, *, count_id, entries: list[tuple[str, int | None]]) -> PPEInventoryCount
```
- Guard `count.status == "draft"` (иначе `InventoryCountNotDraft` → 400).
- Для каждой `(line_id, counted_qty)`: строка должна принадлежать `count_id`+tenant (иначе 404);
  `counted_qty` — `None` (сброс) или `>= 0`. Проставляет `counted_qty`.
- Возвращает обновлённый срез.
- **Граница схема↔сервис:** роут парсит Pydantic-тело `PPEInventoryCountLinesUpdate` в
  `list[tuple[str, int | None]]` (`[(e.line_id, e.counted_qty) for e in payload.entries]`) и передаёт
  сервису — сервис не зависит от Pydantic (как соседние ppe-сервисы принимают простые аргументы).

```python
async def apply_count(session, tenant_id, *, count_id, now: datetime) -> PPEInventoryCount
```
- Guard `count.status == "draft"` (иначе 400). Для каждой строки, где `counted_qty is not None`:
  - грузит **живую** партию (`deleted_at IS NULL`); если партия исчезла/soft-deleted → строка пропускается (defensive);
  - `live = batch.quantity`; если `counted_qty == live` → пропуск (нулевая дельта, проводку не пишем).
    Эта проверка — **advisory** (чтобы не плодить пустые проводки); источник истины — `record_movement`
    (set-to-absolute), который сам перечитает партию и вычислит дельту, так что гонка «остаток изменился
    между проверкой и записью» безопасна (итог = `counted_qty`);
  - иначе `movement = record_movement(session, tenant_id=tenant_id, batch_id=line.batch_id,
    kind="adjustment", quantity=counted_qty, reason=f"inventory {count_id}",
    ref_type="ppe_inventory_count", ref_id=count_id)`; `line.adjustment_movement_id = movement.id`.
- `count.status = "applied"`, `count.applied_at = now`. Возвращает срез. Повторный `apply` → 400.
- **Конкурентный apply.** `PPEInventoryCount` наследует `VersionedMixin` (`base.py`: `version` +
  `version_id_col`) → оптимистичная блокировка. Два параллельных `apply` одного среза: флип
  `draft→applied` бампит `version`, проигравший коммит падает `StaleDataError` на flush → ловим и отдаём
  `409` (двойных проводок не будет). Весь `apply` — в одной транзакции запроса (частично применённый
  срез либо целиком, либо откат).

```python
async def cancel_count(session, tenant_id, *, count_id) -> PPEInventoryCount
```
- Guard `draft` → `status = "cancelled"`. Проводок не пишет.

**Инвариант:** `apply` идёт **через `record_movement`**, не через `_write_movement` напрямую →
«`batch.quantity` только через сервис проводок» держится. Инвентаризация ничего не мутирует в остатке
сама — только просит движок.

### Слой 4 — аддитивная правка `backend/app/modules/ppe/stock.py`

**Это ИЗМЕНЕНИЕ сигнатуры `record_movement`, не pre-existing:** сейчас (`stock.py`) параметров
`ref_type`/`ref_id` в `record_movement` нет; их уже принимает нижележащий `_write_movement`. Добавляем
их в `record_movement` как **опциональные** (default `None`) и прокидываем сквозь — существующие вызовы
(`create_stock_batch` opening-balance, `create_stock_movement` роут) не передают их → поведение идентично:

```python
async def record_movement(session, *, tenant_id, batch_id, kind, quantity,
                          reason=None, occurred_at=None,
                          ref_type: str | None = None, ref_id: str | None = None) -> PPEStockMovement:
    ...
    return await _write_movement(..., ref_type=ref_type, ref_id=ref_id)
```

`_write_movement` уже принимает `ref_type`/`ref_id` — прокидываем сквозь. Единственная правка ledger:
`adjustment`-проводка инвентаризации ссылается на срез (`ref_type="ppe_inventory_count"`, `ref_id=<count.id>`),
журнал→срез. (Существующие вызовы `record_movement` в `create_stock_batch` и `create_stock_movement`
не передают ref → поведение идентично.)

### Слой 5 — схемы `backend/app/schemas/ppe.py` (рядом со stock-схемами, база `BaseSchema`)

```python
class PPEInventoryCountCreate(BaseSchema):
    scope_item_id: str | None = None
    scope_location: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)

class PPEInventoryCountLineInput(BaseSchema):
    line_id: str
    counted_qty: int | None = Field(default=None, ge=0)  # None=не считали; 0=не нашли; ge=0 — только когда int

class PPEInventoryCountLinesUpdate(BaseSchema):
    entries: list[PPEInventoryCountLineInput]

class PPEInventoryCountLineRead(BaseSchema):
    id: str
    batch_id: str
    item_id: str
    batch_no: str
    location: str | None
    item_name: str
    system_qty: int
    counted_qty: int | None
    on_hand: int            # живой batch.quantity на момент чтения
    delta: int | None       # counted_qty - on_hand (None если не сосчитано)
    adjustment_movement_id: str | None

class PPEInventoryCountRead(BaseSchema):     # summary (list / create / apply / cancel)
    id: str
    status: str
    scope_item_id: str | None
    scope_location: str | None
    note: str | None
    applied_at: datetime | None
    created_at: datetime
    line_count: int
    counted_count: int       # строк с counted_qty is not None
    diff_count: int          # строк, где counted_qty задан и != on_hand

class PPEInventoryCountDetail(PPEInventoryCountRead):   # GET by id + после мутаций
    lines: list[PPEInventoryCountLineRead]

class PPEInventoryCountPage(BaseSchema):
    items: list[PPEInventoryCountRead]
    total: int
```

`on_hand`/`delta`/сводные счётчики (`line_count`/`counted_count`/`diff_count`) вычисляются в роуте/сервисе
при сборке ответа, не хранятся. `on_hand` — из **батч-запроса** живых партий строки
(`select(PPEStockBatch.id, PPEStockBatch.quantity).where(id.in_(batch_ids), deleted_at IS NULL)` → map),
`item_name` — из name-map по `item_id` (паттерн `list_stock_levels`, `ppe.py`). Строка, чья партия
soft-deleted/отсутствует в map → `on_hand=0`, `delta` не считается (read-only, при `apply` пропускается).
Никакого ленивого `line.batch` (нет N+1, нет утечки удалённых партий).

### Слой 6 — API `backend/app/api/routes/ppe.py` (за `WarehouseFeatureGate`)

Все роуты: `dependencies=[WarehouseFeatureGate]` (404 когда флаг выкл), `TenantContextValidator.ensure_tenant_context(tenant)`.

| Метод + путь | Доступ | Аудит | Ответ |
|---|---|---|---|
| `POST /stock/inventory/counts` | `EditorAccess` | `@audit_operation("create","ppe_inventory_count")` | `PPEInventoryCountDetail` (201) |
| `GET /stock/inventory/counts` | `ManagerAccess` | — | `PPEInventoryCountPage` (фильтр `status?`, `limit`/`offset`, ETag+304) |
| `GET /stock/inventory/counts/{id}` | `ManagerAccess` | — | `PPEInventoryCountDetail` (строки с live `on_hand`/`delta` = превью) |
| `PATCH /stock/inventory/counts/{id}/lines` | `EditorAccess` | `@audit_operation("update","ppe_inventory_count")` | `PPEInventoryCountDetail` |
| `POST /stock/inventory/counts/{id}/apply` | `EditorAccess` | `@audit_operation("update","ppe_inventory_count")` | `PPEInventoryCountDetail` |
| `POST /stock/inventory/counts/{id}/cancel` | `EditorAccess` | `@audit_operation("update","ppe_inventory_count")` | `PPEInventoryCountDetail` |

- Ошибки зеркалят соседей: `InventoryCountNotFound`→404, `InventoryCountNotDraft`/`ValueError`→400 через
  `_ppe_bad_request`; cross-tenant `id` → 404 (фича невидима); `counted_qty < 0` → 422 (Pydantic `ge=0`).
- «Превью» сложено в `GET .../{id}` (детали считают live `on_hand`+`delta`) — отдельного роута нет.
  Деталь собирается **фиксированным числом запросов** (строки среза + батч-map живых партий с
  `deleted_at IS NULL` + name-map позиций), без per-line ленивой подгрузки (нет N+1, нет утечки
  soft-deleted партий) — см. Слой 5.
- Аудит-глагол `apply`/`cancel` держим в рамках существующего набора (`"update"`); при
  реализации проверить, принимает ли `@audit_operation` произвольные глаголы — если да, допустимо
  `"apply"`/`"cancel"` для читаемости.

### Слой 7 — фронт `frontend/src/pages/warehouse/WarehousePage.tsx` + `api/warehouse.ts`

- `warehouseApi`: `listCounts()`, `createCount(body)`, `getCount(id)`, `patchCountLines(id, entries)`,
  `applyCount(id)`, `cancelCount(id)` + DTO-зеркала (`InventoryCountDto`, `InventoryCountLineDto`,
  `InventoryCountDetailDto`) в стиле существующих `StockMovementDto` / `PPEStockShortageDto`.
- Секция **«Инвентаризация»** на `WarehousePage`:
  - список срезов (бейдж статуса, скоуп, `created_at`/`applied_at`) + форма «Новый срез» (опц. позиция/локация/заметка);
  - детальный вид среза: таблица строк (`batch_no` · локация · система (снимок `system_qty`) · остаток
    (живой `on_hand`) · **редактируемый** ввод факта (`counted_qty`) · бейдж `delta`) с кнопками
    «Сохранить факт» (`patchCountLines`), «Применить» (со сводкой `diff_count`) и «Отменить»;
  - после `apply`/`cancel` грид переходит в read-only (статус ≠ `draft`).

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| `counted_qty = null` (не сосчитано) | строка при apply пропускается (остаток не тронут) |
| `counted_qty = 0` | реальное списание в ноль (`adjustment` до 0) |
| `counted_qty == live on_hand` | нулевая дельта → проводка не пишется (журнал чист) |
| выдача/приход между засевом и apply | apply считает дельту от **живого** остатка → итог = факту |
| партия soft-deleted после засева | строка при apply пропускается (нельзя править удалённую партию) |
| нет партий под фильтр | срез создаётся с нулём строк (валиден, отменяем) |
| `apply`/`patch lines` на не-`draft` срезе | `400` (`InventoryCountNotDraft`) |
| конкурентный `apply` того же среза | `409` (`StaleDataError` от optimistic-lock `version`, `VersionedMixin`) |
| флаг `warehouse` ВЫКЛ | `404` на всех `/stock/inventory/*` (единый контракт gate) |
| cross-tenant `count_id`/`line_id` | `404` (не 403 — фича невидима) |
| `counted_qty < 0` | `422` (Pydantic `ge=0`) |

## Тесты (TDD)

- **Сервис (с сессией, паттерн существующих stock-тестов):**
  - `create_count` засевает строки по фильтру (позиция / локация / весь склад) + снимок `system_qty`;
    пустой матч → 0 строк.
  - `set_line_counts` проставляет `counted_qty` только на `draft` (400 на `applied`); cross-count/tenant строка → 404.
  - `apply_count`: пишет `adjustment` только для введённых строк с дельтой≠0; пропускает несосчитанные
    (`null`) и нулевые; ставит `status="applied"`+`applied_at`; повторный apply → 400.
  - **live-дельта:** выдача/приход между засевом и apply → итог остатка = `counted_qty` (не снимку).
  - `counted_qty=0` → списание в ноль; профицит (`counted>live`) → плюс-проводка; строка с
    soft-deleted партией → пропуск.
  - `cancel_count`: `draft → cancelled`, проводок 0; tenant-iso.
  - `record_movement` c `ref_type`/`ref_id` пишет их в проводку; без них — идентично прежнему.
- **API:** полный цикл (create→patch→get(превью)→apply), flag-off 404, tenant-iso 404, RBAC
  (`ManagerAccess` на read / `EditorAccess` на write), 400 не-draft (apply/patch), 422 `counted_qty<0`,
  ETag+304 на листе.
- **Миграция `wa06`:** upgrade создаёт 2 таблицы + индексы + unique, downgrade дропает (порядок FK);
  прогон только на PG16-гейте (`local_gate.py --db-only`).
- **Фронт:** vitest на новые методы `warehouseApi` (list/create/get/patchLines/apply/cancel) + рендер
  секции (засев/правка факта/apply, read-only после apply); `tsc` 0, `vite build` 0.
- **Гейты:** ruff/black; **OpenAPI baseline** `docs/stabilization/openapi_routes_baseline.json` пере-снят
  (811/653 → +6 роутов + ~7 схем, чистый additive, `--compare` зелёный); Celery guard без изменений (ARCH-4).

## Явно ВНЕ объёма (следующие срезы P10-06)

- Поставщики + провенанс партий; перемещения между локациями; бюджет безопасности; мобильная выдача.
- «Слепой» подсчёт (скрыть `system_qty` от счётчика) — тумблер, отложен (YAGNI).
- Двухподписной approval среза / роли «счётчик vs утверждающий».
- «Найдено без партии» (создать партию в ходе среза) — пока через существующий приход/создание партии.
- Проекция расхождений в Command Center / уведомления по факту `apply`.
- Экспорт ведомости инвентаризации (печатная форма ИНВ-3-подобная).

## Self-Review

- **Placeholder scan:** без TBD/TODO; все слои, сигнатуры и таблицы конкретны.
- **Внутренняя согласованность:** `create_count`/`set_line_counts`/`apply_count`/`cancel_count`,
  DTO `PPEInventoryCount{Create,Read,Detail,Page,Line*}`, поля `status`/`counted_qty`/`system_qty` —
  одинаковы во всех слоях. Дельта считается от live `on_hand` во всех местах (превью и apply);
  `system_qty` — только снимок-справка.
- **Скоуп:** один срез = одна аддитивная миграция (2 таблицы) + один новый сервис-модуль + аддитивная
  правка `record_movement` + 6 роутов + расширение фронта; укладывается в один план реализации.
- **Неоднозначности сняты:** «несосчитано» = `null` (пропуск) vs `0` (списание); «дельта» = от живого
  остатка; «скоуп» = опц. фильтр item/location, гранулярность — партия; apply/cancel — action-роуты.
- **Адверсариальное ревью (4 линзы) вкатано:** `record_movement(ref_type/ref_id)` явно помечен как
  изменение сигнатуры; relationship — house-style `backref` (не `back_populates`); read-path — явные
  батч-запросы с `deleted_at IS NULL` (нет N+1/утечки soft-deleted); конкурентный `apply` защищён
  optimistic-lock `version` → 409; граница схема↔сервис (Pydantic→tuple) прописана; OpenAPI baseline-файл
  назван; `status` — только `default` (новая таблица).

## Анти-грабли

- `status` — VARCHAR, не PG-enum (enum-parity; иначе `InvalidTextRepresentationError` на PG).
- `apply` идёт **через `record_movement`** (чокпоинт цел); `stock.py` правится только аддитивно (`ref_type`/`ref_id`).
- Дельта — от **живого** `batch.quantity`, не от снимка `system_qty` (anti-silent-stale; set-to-absolute самокорректируется).
- `counted_qty=null` ≠ `0`: пропуск против списания — не путать в сервисе и в форме.
- Заморозка после `apply`/`cancel`: правка строк и повторный `apply` на не-`draft` → 400.
- `ref_type/ref_id` (журнал→срез) строкой без FK; `adjustment_movement_id` (строка→журнал) строкой без FK —
  журнал append-only, переживает hard-delete.
- Строка с soft-deleted партией при apply — пропуск (не 400 на весь срез): один разрез не должен падать из-за одной убранной партии.
- Миграция `wa06` чейнится от `wa05` (единственный head); downgrade дропает; только PG16 (SQLite alembic-цепочку не тянет).
- OpenAPI baseline пере-снять `scripts/ci/check_openapi_snapshot.py --snapshot` — обновляет
  **`docs/stabilization/openapi_routes_baseline.json`** (авторитетный baseline, ARCH-4), не старый снапшот.
  Новые 6 роутов: `POST /api/v1/ppe/stock/inventory/counts`, `GET /api/v1/ppe/stock/inventory/counts`,
  `GET /api/v1/ppe/stock/inventory/counts/{id}`, `PATCH .../{id}/lines`, `POST .../{id}/apply`,
  `POST .../{id}/cancel`. Зафиксировать новые счётчики в handoff — иначе ARCH-4 красный.
