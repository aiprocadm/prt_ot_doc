# P10-06 СИЗ склад — срез «Журнал движений склада (честные остатки)» — Design

**Дата:** 2026-07-02
**Контур:** P10-06 СИЗ склад (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники:** СИЗ Срез-1 (удалён orphan `WarehousePPE`, миграция `sz02`) + W-A skeleton (`PPEStockBatch` + `/ppe/stock/*` за флагом `warehouse`, миграция `wa01`) — влиты в main.
**Driver:** brainstorming → writing-plans → subagent-driven-development.

## Цель

Сделать складские остатки **честными**. Сегодня `PPEStockBatch.quantity` меняется только
ручным `PATCH`, а выдача СИЗ работнику (`PPEIssue` / `POST /ppe/issues`) **никак не связана
с партиями и не списывает остаток**. `/ppe/stock/levels` — статичный снимок, а не живой баланс.

Срез вводит **append-only журнал движений** `ppe_stock_movement` и делает `batch.quantity`
живым кэш-балансом, который меняется **только** через сервис проводок. Приход, ручное
списание, корректировка и — главное — **выдача работнику списывает остаток по FIFO**.
Остаток «перед выдачей» становится реальным.

Это спинной хребет складского контура: последующие срезы (мин-остаток/прогноз дефицита,
инвентаризация, поставщики, перемещения) строятся поверх честного баланса.

## Не «дивиденд без миграции»: миграция аддитивная `wa04`

В отличие от недавних срезов СОУТ, здесь **есть** миграция — одна новая таблица
`ppe_stock_movement`. Она **строго аддитивна**: новых колонок в существующих таблицах нет,
бэкофилл не требуется (текущий `quantity` существующих партий = открывающий баланс).
Критерий: миграция создаёт только `ppe_stock_movement` (+индексы); `alembic downgrade`
честно её дропает; валидируется PG16-гейтом.

## Принятые решения (brainstorming)

1. **Семантика остатка — Вариант B (кэш-баланс + append-only журнал).** `batch.quantity` —
   живой on-hand; `ppe_stock_movement` — неизменяемый журнал. Обе записи меняются в одной
   транзакции через единственный сервис. (Отклонены: A — event-sourced on-hand как сумма
   проводок, тяжелит смёрженный `/stock/levels` + требует бэкофилл; C — outbox-реактивное
   списание, ломает синхронный сценарий «остаток перед выдачей».)
2. **Аллокация при выдаче — FIFO авто + явное переопределение.** Явный `batch_id` → списываем
   с него; иначе авто-FIFO по `received_at` (oldest-first), при нехватке в партии — переход на
   следующую. Флаг `warehouse` ВЫКЛ **или** у позиции нет партий → выдача идёт как сейчас, без
   движения (полная обратная совместимость).
3. **Нехватка остатка → отказ 400** (флаг ВКЛ, партии есть, но суммарно/в явной партии не
   хватает). Отличие от «жёсткого FIFO»: при **полном отсутствии** партий у позиции выдача
   **не блокируется** (склад для позиции просто не ведётся).
4. **Сырой `PATCH quantity` убирается.** Количество меняется только проводкой; в
   `PPEStockBatchUpdate` остаются метаданные партии (`batch_no`, `location`, сертификаты).
5. **Списание только в точке выдачи.** Возврат б/у СИЗ на склад не возвращается (гигиена);
   списание выданного — событие личной карточки, не склада. Единственная точка склад-расхода —
   `issue_ppe_item` (и путь `replace_issue`, т.к. он тоже выдаёт новую позицию).
6. **Фронт-скоуп:** секция «Движения» + ручной приход/корректировка на `WarehousePage`. Пикер
   партии в форме выдачи (переопределение FIFO) — отложен (авто-FIFO покрывает основной путь).

## Архитектура

### Слой 1 — модель `backend/app/models/ppe.py :: PPEStockMovement`

`TenantBaseModel` (без `SoftDeleteMixin` — журнал неизменяем).

| Поле | Тип | Смысл |
|---|---|---|
| `item_id` | `ForeignKey("ppeitem.id", ondelete="CASCADE")`, not null, index | позиция каталога |
| `batch_id` | `ForeignKey("ppe_stock_batch.id", ondelete="CASCADE")`, nullable, index | партия (`adjustment` уровня позиции может быть без партии) |
| `kind` | `String(32)`, not null | `receipt` / `issue` / `writeoff` / `adjustment` (VARCHAR, **не** PG-enum — конвенция enum-parity репо) |
| `quantity_delta` | `Integer`, not null | со знаком: `+` приход, `−` расход |
| `occurred_at` | `DateTime(timezone=True)`, not null, default `now()` | момент движения |
| `reason` | `String(255)`, nullable | причина/примечание |
| `ref_type` | `String(64)`, nullable | тип источника, напр. `"ppe_issue"` |
| `ref_id` | `String(36)`, nullable | id источника — **строкой, без FK** (переживает hard-delete выдачи; конвенция `replaces_issue_id` / `contractor_documents.file_id`) |

`StockMovementKind` — `str`-константы (модуль `modules/ppe`), не Python-`Enum`-в-БД.
Индексы: `ix_ppe_stock_movement_item (tenant_id, item_id)`, `ix_ppe_stock_movement_batch (tenant_id, batch_id)`.
Связь `item`/`batch` — `relationship` без backref-мутаций.

### Слой 2 — сервис `backend/app/modules/ppe/` (движок склада)

Чистая функция аллокации (тестируется без БД):
- `allocate_fifo(batches, quantity) -> list[Allocation]` — `batches` отсортированы по
  `received_at` (nulls last), `id` как tiebreaker; списывает oldest-first, при нехватке
  переходит на следующую; возвращает `[(batch_id, taken), ...]`; если суммарного on-hand не
  хватает → `raise InsufficientStockError(requested, available)`.

Сервис проводок (единственная точка мутации `batch.quantity`):
- `record_movement(session, tenant, *, kind, item_id, batch_id?, quantity, reason?, occurred_at?, ref_type?, ref_id?)`
  — валидирует позицию/партию (tenant-scoped, 404), считает знак дельты по `kind`, применяет
  к `batch.quantity` (guard: результат ≥ 0 → иначе `InsufficientStockError`), пишет строку
  журнала. Возвращает созданную проводку.
- `deplete_for_issue(session, tenant, *, item_id, quantity, batch_id?, ref_id) -> list[PPEStockMovement]`
  — если флаг ВЫКЛ или у позиции нет партий → `[]` (без движения); иначе: явный `batch_id`
  (нехватка → 400) или `allocate_fifo`; на каждую задетую партию — `record_movement(kind=issue,
  quantity_delta<0, ref_type="ppe_issue", ref_id=<issue_id>)`.

**Инвариант:** `batch.quantity` меняется исключительно через `record_movement`. Прямые
`setattr(batch, "quantity", ...)` вне сервиса запрещены (снимаем из `update_stock_batch`).

Создание партии (`POST /stock/batches`) с `quantity=N`: пишет **стартовую проводку**
`receipt +N` (`ref_type="batch_open"`), чтобы журнал новых партий был полон. Существующие
партии skeleton'а живут с текущим `quantity` как открывающим балансом — строки-проводки для
них нет (задокументировано; для честности будущей инвентаризации достаточно).

### Слой 3 — API `backend/app/api/routes/ppe.py` (за `WarehouseFeatureGate`)

- `POST /ppe/stock/movements` — ручной `receipt` / `writeoff` / `adjustment` (**не** `issue` —
  тот только из потока выдачи; передача `kind=issue` сюда → 400). Тело `PPEStockMovementCreate`:
  `item_id` **или** `batch_id`, `kind`, `quantity` (>0), `reason?`, `occurred_at?`.
  Права `EditorAccess`, `@audit_operation("create", "ppe_stock_movement")`. Нехватка → 400.
- `GET /ppe/stock/movements` — список, фильтры `item_id` / `batch_id` / `kind`, пагинация
  (`limit`/`offset`), сорт по `occurred_at DESC, id`, `compute_list_etag`, права `ManagerAccess`.
- `GET /ppe/stock/levels` — **форма не меняется**; теперь честный (сумма живых `quantity`).
- `PATCH /ppe/stock/batches/{id}` — из `PPEStockBatchUpdate` **удаляется поле `quantity`**.
  → OpenAPI baseline пере-снимается (`--snapshot`, санкционированное аддитивное изменение
  контракта; фиксируется в handoff).

Схемы (`backend/app/schemas/ppe.py`): `PPEStockMovementCreate`, `PPEStockMovementRead`,
`PPEStockMovementPage`.

### Слой 4 — интеграция с выдачей `issue_ppe_item` / `replace_issue`

- `PPEIssueCreate` (+`PPEIssueReplaceRequest`) получает опциональный `batch_id: str | None`.
- `create_issue` / `replace_issue_endpoint` после успешного создания выдачи вызывают
  `deplete_for_issue(..., item_id=issue.item_id, quantity=issue.quantity, batch_id=payload.batch_id,
  ref_id=issue.id)` в той же транзакции.
- Существующий `PPE_ISSUED` outbox-эвент **не трогаем**.
- Обратная совместимость: флаг ВЫКЛ или нет партий → `deplete_for_issue` возвращает `[]`,
  выдача идентична текущей.

### Слой 5 — фронтенд `frontend/src/pages/warehouse/WarehousePage.tsx` + `api/warehouse.ts`

- `warehouseApi.listMovements(params)`, `createMovement(body)`.
- Секция **«Движения»**: таблица последних проводок (позиция, тип, ±кол-во, дата, причина) +
  форма ручного прихода/корректировки (выбор позиции/партии, тип, кол-во, причина).
- Остатки (`/stock/levels`) уже отображаются — теперь живые; добавить не нужно.

## Обработка ошибок

| Ситуация | Ответ |
|---|---|
| Нехватка остатка (явная партия или суммарно FIFO) | `400` «недостаточно остатка» (`InsufficientStockError` → `_ppe_bad_request`) |
| `kind=issue` в `POST /stock/movements` | `400` (ручной эндпоинт не создаёт выдачные движения) |
| Неизвестная позиция/партия | `404` (tenant-scoped) |
| Флаг `warehouse` ВЫКЛ | `404` на `/stock/*` (как сейчас); выдача — без движения |
| Cross-tenant `batch_id`/`item_id` | `404` (не 403 — фича невидима) |

## Тестирование (TDD)

- **Юнит (чистый домен):** `allocate_fifo` — одна партия / несколько партий / точное совпадение
  / нехватка (raise) / порядок oldest-first при равных/nulls `received_at`.
- **Сервис:** `record_movement` receipt(+)/writeoff(−)/adjustment(±) меняет `batch.quantity`
  и пишет журнал; guard on-hand ≥ 0; `deplete_for_issue` — FIFO по нескольким партиям,
  explicit batch_id, флаг ВЫКЛ → `[]`, нет партий → `[]`; создание партии пишет стартовый receipt.
- **API:** CRUD движений, фильтры `item/batch/kind`, ETag + 304, tenant-iso (cross-tenant 404),
  400 на нехватку, 400 на `kind=issue`; выдача с флагом ВКЛ списывает FIFO; `PATCH batch`
  больше не принимает `quantity`.
- **Миграция:** `test_wa04_ppe_stock_movement_migration.py` — upgrade создаёт таблицу+индексы,
  downgrade дропает; прогон только на PG16-гейте (`local_gate.py --db-only`).
- **Фронт:** vitest на `warehouseApi` (listMovements/createMovement) + рендер секции;
  `tsc` 0, `npm run build` 0.
- **Гейты:** ruff/black; OpenAPI snapshot (пере-снят из-за нового контракта); Celery guard.

## Acceptance

- Приход/списание/корректировка через `POST /stock/movements` меняют `/stock/levels` (честный баланс).
- Выдача СИЗ при флаге ВКЛ списывает остаток по FIFO; `/stock/levels` уменьшается; создаются
  проводки `issue` с `ref_id` выдачи.
- Явный `batch_id` в выдаче списывает нужную партию; нехватка → 400.
- Флаг ВЫКЛ / нет партий → выдача работает как прежде (регресс существующих тестов зелёный).
- Миграция `wa04` аддитивна, PG16-гейт зелёный; OpenAPI baseline обновлён и зафиксирован.
- `P10-06` в `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`: статус уточнён (skeleton → +журнал движений).

## Отложено (следующие срезы P10-06)

- Мин-остаток / точка заказа / прогноз дефицита (сигналы `below_minimum`).
- Инвентаризация (`ppe_inventory_count`, preview/apply реконсиляции).
- Поставщики + провенанс партий.
- Перемещения между локациями (`transfer` — from/to партия).
- Пикер партии в форме выдачи (UI-переопределение FIFO).
- Стартовые проводки-бэкофилл для существующих skeleton-партий (не требуется для корректности).
- Мобильная выдача (offline-путь, контур W4).

## Анти-грабли

- `ref_type`/`ref_id` **строкой, без FK** — журнал переживает hard-delete выдачи.
- `kind` — VARCHAR, не PG-enum (enum-parity репо; иначе `InvalidTextRepresentationError` на PG).
- Инвариант «`quantity` только через сервис» — снять прямую правку `quantity` из `update_stock_batch`.
- Списание — только при выдаче (не при возврате/списании выданного): один разрез в смёрженный поток.
- FIFO tiebreaker по `id` — детерминизм при равных `received_at` (иначе флак в тестах на PG/SQLite).
- Транзакционность: движение и мутация `batch.quantity` — в одной сессии/flush; частичное
  FIFO-списание по нескольким партиям либо целиком, либо откат (одна транзакция запроса).
- Alembic на SQLite исторически не гоняется (initial_schema JSONB) — миграцию `wa04` валидирует
  только PG16-гейт.
