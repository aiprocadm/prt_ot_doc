# P10-06 СИЗ склад — срез «Поставщики (справочник + провенанс партий + закупочный дозаказ)» — Design

**Дата:** 2026-07-04
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники (влиты в main):** W-A skeleton (`PPEStockBatch` + `/ppe/stock/*` за флагом `warehouse`, `wa01`) → «Журнал движений» (`PPEStockMovement` append-only, `wa04`, FIFO-списание, честный `/stock/levels`, PR #720) → «Мин-остаток + прогноз дефицита» (`ppeitem.min_stock`, `wa05`, `GET /ppe/stock/shortages`, PR #721) → «Инвентаризация» (`ppe_inventory_count[_line]`, `wa06`, `adjustment`-проводки, PR #722) → «Перемещения между локациями» (`kind=transfer`, `wa07`, `/stock/transfers` + `/stock/levels/by-location`, PR #724).
**Driver:** brainstorming → writing-plans → subagent-driven-development.
**Head-миграция на старте:** `20260704_wa07_ppe_stock_batch_location_unique` (единственный head — проверено `glob` versions). Новая миграция `wa08` чейнится от неё.

## Цель

Дать складу СИЗ **провенанс поставщика** и **закупочный дозаказ** поверх честного остатка, не трогая
инвариант «`batch.quantity` меняется только проводкой»:

1. **Справочник поставщиков** — нормализованная master-data сущность `PPESupplier` (название, ИНН,
   контакт), переиспользуемая на многих партиях.
2. **Провенанс партии** — nullable FK `PPEStockBatch.supplier_id`: «эта партия пришла от вендора X».
   Позволяет проследить бракованную партию до поставщика и фильтровать остаток/сертификаты по нему.
3. **Закупочный слой** — отчёт дефицита (`GET /ppe/stock/shortages`) начинает показывать «у кого
   дозаказать позицию», а новый `GET /ppe/stock/reorder` группирует дефицит по поставщикам в **черновик
   заявки** (вычисляемый + экспортируемый список, НЕ персистентная сущность-PO).

Всё за пилотным флагом `warehouse`. Срез **чисто аддитивный** (новая таблица + две nullable-колонки), и
закупочный слой — единственное место, где он касается существующего кода (движок `compute_shortages`).

## Принятые решения (brainstorming, 2026-07-04)

1. **Объём = «справочник + закупки»** (не только текстовое поле провенанса). Нормализованная сущность
   `PPESupplier` + провенанс-FK на партии + связка с движком дефицита. (Отклонён вариант «только
   текстовое поле `supplier_name` на партии» — теряет дедуп/переиспользование/отчётность; отклонён
   вариант «только справочник без закупок» — пользователь явно выбрал закупочную связку.)
2. **«Поставщик позиции» для подсказки дозаказа = явное поле + fallback на историю.** Явное
   `PPEItem.preferred_supplier_id` (админ выбирает основного вендора); если не задано — fallback на
   **последнего по истории** поставщика партий этой позиции. (Отклонён чистый «вывод из истории» — «магия»,
   неочевидная пользователю; отклонён чистый «явное поле» — пустое поле = нет подсказки даже при явной
   истории закупок.)
3. **Глубина дозаказа = показать поставщика в дефиците + сводный черновик заявки.** Строки
   `/stock/shortages` получают поля резолвнутого поставщика; новый `GET /ppe/stock/reorder` группирует
   below-threshold дефицит по поставщикам. Черновик — **вычисляемый JSON + экспорт на фронте**, НЕ новая
   персистентная сущность-заявка (PO-системы нет; персистентная заявка + ЭДО-роуминг — отдельный крупный
   срез в follow-up).
4. **Справочник «Лёгкий»:** `name` (обяз.) + `inn` + `contact_email` + `contact_phone`. CRUD
   create/list/get/patch/soft-delete + секция на `WarehousePage`. (Отклонён «расширенный» с адрес/КПП/сайт —
   YAGNI для среза; отклонён «минимальный» name+inn — контакт нужен для «кому звонить» в дозаказе.)
5. **Провенанс на партии, не на проводке.** `supplier_id` живёт на `PPEStockBatch` (провенанс лота);
   приходная проводка наследует поставщика через партию — **новых колонок в журнал не добавляем**.
6. **Уникальность справочника — только по имени** `(tenant_id, name)` (зеркало `uq_ppe_item_name`).
   Unique по ИНН — follow-up (ИНН информационный, nullable). Soft-deleted тёзка занимает слот имени — то же
   поведение, что у `PPEItem` (консистентно, не find-or-create, squatter не ломает).
7. **Инвариант честного остатка не трогается.** Поставщик — метаданные; `_write_movement`/`record_movement`/
   `Σdelta`-математика не меняются. Обязательный якорь-тест: существующие инварианты остатка зелёные.

## Архитектура

### Слой 1 — модель `backend/app/models/ppe.py` (новая сущность + 2 nullable-FK, аддитивно)

**Новая `PPESupplier`** (после `PPEItem`, до `PPEIssue` — рядом с master-data СИЗ):

```python
class PPESupplier(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ppe_supplier"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ppe_supplier_name"),
    )
```

**Провенанс — `PPEStockBatch.supplier_id`** (nullable FK, `ondelete="SET NULL"`, индекс):

```python
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppe_supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier: Mapped["PPESupplier | None"] = relationship("PPESupplier")
```

**Явный поставщик позиции — `PPEItem.preferred_supplier_id`** (nullable FK, `ondelete="SET NULL"`, индекс):

```python
    preferred_supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppe_supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preferred_supplier: Mapped["PPESupplier | None"] = relationship(
        "PPESupplier", foreign_keys=[preferred_supplier_id]
    )
```

- `ondelete="SET NULL"` — согласуется с `PPENorm.item_id`/`PPEIssue.item_id`; поставщик soft-удаляется,
  но hard-delete не должен осиротить партию/позицию.
- `relationship` — house-style `relationship("PPESupplier")`; для `PPEItem` явный `foreign_keys=[...]`
  (единственная FK на supplier у Item, но указываем явно — читаемость + защита от будущих FK).

### Слой 2 — миграция `wa08` (чисто аддитивная)

`backend/app/migrations/versions/20260704_wa08_ppe_supplier.py`:
- `revision = "20260704_wa08_ppe_supplier"`, `down_revision = "20260704_wa07_ppe_stock_batch_location_unique"`.
- `upgrade` — **порядок важен** (таблица до FK-колонок, которые на неё ссылаются):
  1. `op.create_table("ppe_supplier", ...)` — колонки `TenantBaseModel` (`id`, `tenant_id`, `created_at`,
     `updated_at`) + `SoftDeleteMixin` (`deleted_at`) + `name`/`inn`/`contact_email`/`contact_phone`;
     `UniqueConstraint("tenant_id","name", name="uq_ppe_supplier_name")`; индекс на `tenant_id` по образцу
     соседних таблиц.
  2. `op.add_column("ppe_stock_batch", sa.Column("supplier_id", sa.String(...), nullable=True))` +
     `op.create_foreign_key(..., "ppe_stock_batch", "ppe_supplier", ["supplier_id"], ["id"], ondelete="SET NULL")` +
     `op.create_index("ix_ppe_stock_batch_supplier", "ppe_stock_batch", ["supplier_id"])`.
  3. `op.add_column("ppeitem", sa.Column("preferred_supplier_id", ...))` + FK + индекс
     `ix_ppeitem_preferred_supplier`.
- `downgrade` — **реверс**: drop index+FK+column у `ppeitem`, затем у `ppe_stock_batch`, затем
  `op.drop_table("ppe_supplier")`. Честный (не `pass`).
- **Критерий:** PG16-гейт (`scripts/ci/local_gate.py --db-only`) зелёный — round-trip
  upgrade→downgrade→upgrade без ошибок; чисто аддитивно, enum нет, backfill нет.
- **Анти-грабли:** id-колонки — тот же тип, что у соседних PPE-таблиц (String(36)/тот же, что
  `TenantBaseModel.id`); именованные FK-констрейнты (`fk_...`) — иначе downgrade `drop_constraint` по
  автосгенерированному имени ненадёжен на разных БД. Alembic на SQLite исторически не гоняется
  (initial_schema JSONB) — миграцию валидирует только PG-гейт; unit-тесты строят схему через
  `metadata.create_all`.

### Слой 3 — сервис справочника `backend/app/modules/ppe/suppliers.py` (новый модуль)

Тонкий CRUD (зеркало item-CRUD в `routes/ppe.py`, но вынесен в модуль для изоляции). Чистые async-функции
над сессией:

```python
async def create_supplier(session, *, tenant_id, name, inn=None,
                          contact_email=None, contact_phone=None) -> PPESupplier
async def list_suppliers(session, tenant_id, *, limit, offset) -> tuple[list[PPESupplier], int]
async def get_supplier(session, tenant_id, supplier_id) -> PPESupplier   # None → SupplierNotFound
async def update_supplier(session, tenant_id, supplier_id, **fields) -> PPESupplier
async def soft_delete_supplier(session, tenant_id, supplier_id) -> None   # ставит deleted_at
```

- `SupplierNotFound(Exception)` — маппится роутом в 404 (как `StockBatchNotFound`).
- Дубль имени: `create/update` ловит `IntegrityError` (unique `uq_ppe_supplier_name`) → доменное
  `SupplierNameConflict` → роут в 409. (Либо pre-check select по имени; но `IntegrityError`-путь надёжнее
  против гонки — паттерн route-level `except IntegrityError→409` из среза переносов.)
- `list_suppliers` tenant-scoped, `deleted_at IS NULL`, `order_by(name.asc())`, `limit/offset` + `count`.

### Слой 4 — закупочный слой в `backend/app/modules/ppe/stock.py` (аддитивная правка `compute_shortages` + резолвер)

**Резолв поставщика позиции** — внутри `compute_shortages` (у него уже загружены `items` и `item_ids`;
держим в одном месте, избегаем импорт-цикла `stock.py`→`suppliers.py`). Батчами, без N+1:

1. **Явные:** из уже загруженных `items` — `{item.id: item.preferred_supplier_id}` для непустых.
2. **История (fallback)** — для позиций без явного: один запрос всех партий с `supplier_id IS NOT NULL`
   по `item_ids`, поля `(item_id, supplier_id, received_at, created_at)`; в Python выбрать **последнего**
   per item: `received_at desc` (NULL last), затем `created_at desc` — первый = последний закупленный.
3. **Загрузка карточек** — один `select(PPESupplier).where(id.in_(resolved_ids), deleted_at IS NULL)` →
   map `{id: supplier}`. Soft-deleted поставщик → трактуем как «нет поставщика» (source=None).

`ShortageRow` (dataclass) получает поля: `supplier_id: str | None`, `supplier_name: str | None`,
`supplier_inn: str | None`, `supplier_contact: str | None` (email или phone, email приоритетнее),
`supplier_source: str | None` (`"explicit"` | `"history"` | `None`).

**Черновик дозаказа** — новая чистая группировка `build_reorder_draft(rows) -> ReorderDraft`:
- берёт `ShortageRow` c `below_threshold and deficit > 0`;
- группирует по `supplier_id` (None → группа `unassigned`);
- на группу: `supplier` (id/name/inn/contact или None), `lines: [{item_id, item_name, deficit}]`,
  `line_count`, `total_deficit = Σ deficit`;
- сортировка: группы с поставщиком по `supplier_name`, `unassigned` — последней.

```python
@dataclass(slots=True, frozen=True)
class ReorderLine:
    item_id: str
    item_name: str
    deficit: int

@dataclass(slots=True, frozen=True)
class ReorderGroup:
    supplier_id: str | None
    supplier_name: str | None
    supplier_inn: str | None
    supplier_contact: str | None
    lines: list[ReorderLine]
    line_count: int
    total_deficit: int

@dataclass(slots=True, frozen=True)
class ReorderDraft:
    groups: list[ReorderGroup]
    total_lines: int
    total_deficit: int
```

### Слой 5 — схемы `backend/app/schemas/ppe.py` (база `BaseSchema`, `model_validate` ORM-mode)

```python
class PPESupplierCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)

class PPESupplierUpdate(BaseSchema):   # все опциональны (partial PATCH, exclude_unset)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)

class PPESupplierRead(BaseSchema):
    id: str
    name: str
    inn: str | None
    contact_email: str | None
    contact_phone: str | None

class PPESupplierPage(BaseSchema):
    items: list[PPESupplierRead]
    total: int
```

Расширения существующих схем (аддитивно, поля nullable — совместимость):
- `PPEStockBatchCreate` / `PPEStockBatchUpdate` / `PPEStockBatchRead` — `+ supplier_id: str | None`.
- `PPEItemCreate` / `PPEItemUpdate` / `PPEItemRead` — `+ preferred_supplier_id: str | None`.
- `PPEStockShortageRead` — `+ supplier_id / supplier_name / supplier_inn / supplier_contact /
  supplier_source` (все nullable).
- Новые reorder-схемы `PPEReorderLineRead` / `PPEReorderGroupRead` / `PPEReorderDraftRead`
  (зеркало dataclass-ов слоя 4).

### Слой 6 — API `backend/app/api/routes/ppe.py`

**Справочник (5 роутов, зеркало `/items`, за `WarehouseFeatureGate`):**

| Метод + путь | Доступ | Аудит | Ответ |
|---|---|---|---|
| `POST /suppliers` | `EditorAccess` | `@audit_operation("create","ppe_supplier")` | `PPESupplierRead` (201); дубль имени→409 |
| `GET /suppliers` | `ManagerAccess` | — | `PPESupplierPage` (`limit`/`offset`, ETag+304 — паттерн `list_items`) |
| `GET /suppliers/{id}` | `ManagerAccess` | — | `PPESupplierRead`; нет/cross-tenant→404 |
| `PATCH /suppliers/{id}` | `EditorAccess` | `@audit_operation("update","ppe_supplier")` | `PPESupplierRead`; дубль→409 |
| `DELETE /suppliers/{id}` | `EditorAccess` | `@audit_operation("delete","ppe_supplier")` | 204 (soft-delete) |

- Маппинг ошибок: `SupplierNotFound`→404, `SupplierNameConflict`/`IntegrityError`→409 (дедик. helper
  `_ppe_supplier_conflict` — существующий `_ppe_conflict` имеет фиксированный code
  `PPE_INVENTORY_COUNT_CONFLICT`; добавить супплаер-скоуп-вариант, чтобы код проблемы был честным).
- `require_warehouse_feature` (404 когда флаг выкл) на всех.

**Провенанс (правка существующих роутов, аддитивно):**
- `create_stock_batch` / `update_stock_batch` — принимают и пишут `supplier_id` (валидация: если задан —
  поставщик существует в тенанте, иначе 400/404). `PPEStockBatchRead` возвращает `supplier_id`.
- `create_item` / `update_item` — принимают/пишут `preferred_supplier_id` (аналогичная валидация).

**Закупки (2 правки/роута):**
- `list_stock_shortages` (`GET /stock/shortages`) — прокидывает новые supplier-поля из `ShortageRow` в
  `PPEStockShortageRead` (контракт расширяется аддитивно).
- **`GET /stock/reorder`** (новый, `ManagerAccess`, `WarehouseFeatureGate`): зовёт `compute_shortages(...,
  only_below=True)` → `build_reorder_draft(rows)` → `PPEReorderDraftRead`. Параметр `window_days` (как у
  shortages). Без ETag (вычисляемый агрегат, как shortages).

**Критичная интеграция переносов:** `transfer_stock → _find_or_create_dest_batch` ([stock.py]) при
создании партии-приёмника **должен копировать `supplier_id=source.supplier_id`** рядом с уже копируемым
провенансом (`received_at`/`certificate_no`/`certificate_expires_at`) — иначе перенесённый лот теряет
вендора. Покрывается тестом.

### Слой 7 — фронт `frontend/src/pages/warehouse/WarehousePage.tsx` + `api/warehouse.ts`

- `warehouseApi` + DTO-зеркала: `listSuppliers/createSupplier/updateSupplier/deleteSupplier`
  (`SupplierDto`, `SupplierCreateDto`), `getReorderDraft()` (`ReorderDraftDto`); расширить
  `StockBatchDto`(+`supplier_id`), `PPEItemDto`(+`preferred_supplier_id`), `PPEStockShortageDto`(+supplier-поля).
- Секция **«Поставщики»**: список + форма создания/редактирования (name обяз. / ИНН / email / телефон) +
  кнопка soft-delete. Дубль имени → баннер ошибки.
- **Форма партии** (в секции «Движения»/приход): пикер поставщика (`<select>` из загруженных поставщиков;
  пусто = без поставщика).
- Секция **«Дефицит / мин-остаток»**: колонка «Поставщик» (название + бейдж источника явный/история) +
  инлайн-пикер, PATCH-ящий `preferred_supplier_id` позиции (даёт явному полю UI без экрана редактирования
  позиции — согласуется с тем, что `min_stock` тоже API-only).
- Новый вид **«Дозаказ»**: карточки по поставщикам из `getReorderDraft()` (поставщик + контакт + строки
  {позиция, дефицит} + итог), группа `unassigned` последней; кнопка «Копировать»/CSV — на фронте.
- Ошибки submit — в баннере (shared error-state, как в прошлых срезах).

## Обработка ошибок / edge-cases

| Случай | Поведение |
|---|---|
| поставщик не найден / cross-tenant / soft-deleted | `404` (`SupplierNotFound`; фича невидима, не 403) |
| дубль имени поставщика (create/update) | `409` (`uq_ppe_supplier_name` → `IntegrityError`/`SupplierNameConflict`) |
| пустое `name` поставщика | `422` (схема `min_length=1`) |
| `supplier_id` партии/позиции указывает на несуществующего/чужого поставщика | `400`/`404` (валидация в роуте) |
| партия с `supplier_id`, поставщик потом soft-удалён | партия хранит id; read показывает поставщика по map (soft-deleted → трактуем как «нет» в резолве дозаказа) |
| перенос партии с поставщиком | приёмник копирует `supplier_id` источника (тест-якорь) |
| позиция без явного поставщика, но с историей закупок | дозаказ подставляет последнего по истории (`source="history"`) |
| позиция без явного и без истории | группа `unassigned` в дозаказе; в shortages supplier-поля = null |
| флаг `warehouse` ВЫКЛ | `404` на `/suppliers*` и `/stock/reorder` |
| остаток честного баланса | НЕ затронут: supplier — метаданные, `Σdelta`/`_write_movement` не меняются (якорь `before==after`) |

## Тесты (TDD)

- **Модель/схема:** `PPESupplier` round-trip (`metadata.create_all`); `PPESupplierRead.model_validate`;
  `PPEStockBatchRead`/`PPEItemRead` отдают новые nullable-поля.
- **Миграция `wa08`:** upgrade создаёт таблицу+2 колонки+FK+индексы; downgrade реверсит; round-trip только
  на PG16-гейте (`local_gate.py --db-only`).
- **Сервис справочника:** create/list(пагинация+порядок)/get/patch/soft-delete; дубль имени→конфликт;
  tenant-iso (чужой поставщик → `SupplierNotFound`); soft-deleted не в списке.
- **Провенанс:** партия с `supplier_id` создаётся/читается; перенос копирует `supplier_id` в приёмник;
  **инвариант `on_hand` до==после переноса** не затронут supplier-полем.
- **Резолв поставщика (юнит + сервис):** явный побеждает историю; при пустом явном — fallback на
  последнего по истории (tie-break `received_at desc`→`created_at desc`); soft-deleted резолвнутый → None;
  позиция без данных → None.
- **Дозаказ:** `build_reorder_draft` группирует по поставщику, `unassigned` последней, `total_deficit`
  корректен, only-below фильтр; API `GET /stock/reorder` форма ответа + flag-off 404.
- **Shortages контракт:** `GET /stock/shortages` отдаёт supplier-поля (явный/история/none).
- **RBAC:** `ManagerAccess` на read, `EditorAccess` на write справочника; `WarehouseFeatureGate` на всех.
- **Фронт:** vitest WarehousePage — секция поставщиков (CRUD), пикер поставщика в форме партии, колонка
  поставщика + инлайн-пикер в дефиците, вид дозаказа; `tsc` 0, `vite build` 0.
- **Гейты:** ruff/black; **OpenAPI baseline** `docs/stabilization/openapi_routes_baseline.json` пере-снят
  (820/665 → +6 роутов [5 suppliers + reorder] + ~7 схем + расширенные поля, чистый additive, `--compare`
  зелёный); Celery guard без изменений (ARCH-4).

## Явно ВНЕ объёма (следующие срезы / follow-up P10-06)

- Unique по ИНН (`(tenant_id, inn) WHERE inn IS NOT NULL` частичный) — ИНН пока информационный.
- Персистентная сущность-заявка/PO + жизненный цикл + ЭДО-роуминг заявок (дозаказ = вычисляемый черновик).
- Полный экран редактирования позиции СИЗ (preferred_supplier ставится инлайн-пикером в дефиците).
- Мультипоставщик-на-позицию, прайс-листы, сроки поставки, метрики качества/надёжности поставщика.
- Reorder-CSV как backend-endpoint (сейчас экспорт — на фронте).
- Бюджет безопасности; мобильная выдача (оставшиеся пункты P10-06 после этого среза).

## Self-Review

- **Placeholder scan:** без TBD/TODO; все слои, сигнатуры, таблицы, поля конкретны.
- **Внутренняя согласованность:** `PPESupplier`(name/inn/contact_email/contact_phone),
  `supplier_id`/`preferred_supplier_id`, DTO `PPESupplier{Create,Update,Read,Page}`, reorder-датаклассы и
  их схемы, supplier-поля `ShortageRow`↔`PPEStockShortageRead` — одинаковы во всех слоях. Резолв (явный→
  история→none) описан один раз и используется и в shortages, и в reorder.
- **Скоуп:** один срез = одна аддитивная миграция `wa08` + новая `PPESupplier` + 2 nullable-FK + модуль
  `suppliers.py` + аддитивная правка `stock.py` (резолв + `build_reorder_draft`) + 6 роутов + правки
  существующих (batch/item/shortages) + фронт; укладывается в один план (~12–14 TDD-задач).
- **Неоднозначности сняты:** «черновик заявки» = вычисляемый JSON + экспорт (НЕ персистентная сущность);
  поставщик позиции = явное поле + fallback на историю; провенанс на партии (не на проводке); уникальность
  справочника — по имени; soft-deleted поставщик трактуется как «нет» в резолве дозаказа.
- **Адверсариальные линзы вкатаны:** инвариант честного остатка не тронут (supplier — метаданные, якорь
  `before==after`); резолв без N+1 (батч-запросы); soft-deleted-поставщик не «оживает» в дозаказе;
  критичная копия `supplier_id` в переносе помечена и покрыта тестом; `ondelete=SET NULL` не осиротит;
  миграция аддитивная с честным downgrade + именованные FK; дубль имени через `IntegrityError`→409 (гонка);
  OpenAPI baseline-файл и счётчики названы.

## Анти-грабли

- **Инвариант остатка не трогается:** `_write_movement`/`record_movement`/`Σdelta` не меняются; supplier —
  только метаданные. Обязательный якорь-тест: `on_hand` до/после переноса и приходов неизменен.
- **Критичная копия провенанса в переносе:** `_find_or_create_dest_batch` должен добавить
  `supplier_id=source.supplier_id` — легко пропустить, покрыть тестом.
- **Резолв поставщика — батчами, без N+1:** один запрос истории партий + один запрос карточек поставщиков
  на весь `item_ids`, не per-item lazy `item.preferred_supplier`.
- **Soft-deleted поставщик:** не в списке справочника; в резолве дозаказа резолвнутый soft-deleted →
  трактуется как «нет поставщика» (иначе «мёртвый» вендор всплывает в заявке).
- **`ondelete="SET NULL"`** на обоих FK (не CASCADE) — hard-delete поставщика не должен удалять партии/позиции.
- **Миграция `wa08` чейнится от `wa07`** (единственный head); **чисто аддитивная** — таблица до FK-колонок в
  upgrade, реверс в downgrade; именованные FK-констрейнты; PG16-gate round-trip; SQLite alembic не гоняется.
- **Уникальность справочника:** `UniqueConstraint(tenant_id, name)` (зеркало `PPEItem`); soft-deleted тёзка
  занимает слот (консистентно с `PPEItem`, не find-or-create). Дубль → `IntegrityError`→409 (не pre-check —
  устойчиво к гонке).
- **409-код честный:** не переиспользовать `_ppe_conflict` (фикс. code `PPE_INVENTORY_COUNT_CONFLICT`) для
  дубля поставщика — добавить `_ppe_supplier_conflict` со своим кодом.
- **Черновик дозаказа — вычисляемый**, без персистентной таблицы/lifecycle; `unassigned`-группа для позиций
  без резолва (иначе дефицит без поставщика молча исчезает из заявки).
- **OpenAPI baseline пере-снять** `scripts/ci/check_openapi_snapshot.py --snapshot` (обновляет
  `docs/stabilization/openapi_routes_baseline.json`, ARCH-4). Новые роуты: `POST/GET /ppe/suppliers`,
  `GET/PATCH/DELETE /ppe/suppliers/{id}`, `GET /ppe/stock/reorder`. Зафиксировать счётчики (820/665 →
  ~826/~672) в handoff — иначе ARCH-4 красный. Скрипт требует `$env:PYTHONPATH="backend"`.
- **Операционка (из прошлых handoff):** в git-worktree нет `.venv`/`node_modules`; бэкенд-тесты — глобальным
  `Python313\python.exe -m pytest` (Git-Bash сегфолтит); холодный импорт ~2-3 мин → pytest/OpenAPI с
  таймаутом 600000мс ОДИН раз без ретрая; black может ломать substring-ассерты миграций (нормализовать
  пробелы или re-run после black).
