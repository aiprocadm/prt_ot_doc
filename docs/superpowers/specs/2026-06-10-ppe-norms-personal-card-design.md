# СИЗ Срез-1: нормы выдачи + личная карточка 766н + жизненный цикл выдачи — Design

**Дата:** 2026-06-10
**Контур:** СИЗ / склад (vNext §12, ТЗ раздел B)
**Ветка:** `feat/ppe-norms-personal-card` (от `main`@`67e9468`)
**Нормативный ориентир:** Приказ Минтруда РФ от 29.10.2021 № 766н «Об утверждении Правил обеспечения работников средствами индивидуальной защиты и смывающими средствами»

## 1. Проблема

Аудит 2026-06-07 ([[tz-section-b-ground-truth]]) зафиксировал СИЗ-контур на ~25–30% с двумя анти-паттернами:

1. **«Schema theater»:** богатое семейство B (`safety_core.py`: `PPECatalog`, `PPENorm`/`ppe_norms`, `PPENormItem` с size_grid и полиморфной привязкой, `PPEIssue`/`ppe_issues`, `PPEPersonalCard`, `PPEPersonalCardItem`) существует в ORM и миграции `next58`, но **не имеет ни одного эндпоинта**. Вдобавок миграция next58 ссылается на таблицу `persons`, а не `person` (ловушка), а имена классов `PPENorm`/`PPEIssue` дублируют живые классы из `models.py` (латентный риск `configure_mappers`, см. [[orm-duplicate-class-names]]).
2. **Нормы без write-path:** живая модель `PPENorm` (`models.py:1400`, position+hazard+item_name) заполняется только напрямую в БД — CRUD-API нет. «Личная карточка» — лишь on-the-fly payload для рендеринга документов (`domains/ppe/service.py:build_personal_card_payload`), без статусов и реквизитов 766н.
3. **Мёртвый орфан** `WarehousePPE` (`models.py:2321`) — таблица из initial_schema без эндпоинтов, сервисов и связей.

При этом живое семейство A работает end-to-end: `PPEItem`/`PPEIssue`/`PPEStockBatch` имеют CRUD `/ppe/*`, outbox-события `PPE_ISSUED`/`PPE_RETURNED`, фронт-страницу `PpePage`, аналитику и data-quality правило.

## 2. Цель среза (deliverable)

1. **Нормы выдачи получают write-path** — CRUD `/ppe/norms` с привязкой к каталогу (`item_id`), 409 на дубль, tenant-изоляция.
2. **Личная карточка по форме 766н** — `GET /ppe/employees/{person_id}/card`: шапка (работник, должность, размеры/антропометрия), «положено» (объединение норм), «выдано/возвращено» (с № сертификата, % износа, ссылкой на подписанный документ), timeline, статусы строк `OK/DUE_SOON/OVERDUE/MISSING`.
3. **Явный жизненный цикл выдачи** — операции `return`/`writeoff`/`replace` с FSM-валидацией (вместо свободного PATCH статуса).
4. **Автоматизация** — beat `ppe.expiry.tick` + событие `PPE_REPLACEMENT_DUE`.
5. **Закрытие архитектурного долга** — семейство B и `WarehousePPE` удаляются из ORM (таблицы в БД не трогаются).

Выбор подхода: **A — эволюция живой схемы** (расширить семейство A под 766н + домен по паттерну medical/contractors). Отвергнуты: B — новая богатая норм-схема ЕТН (третья норм-схема в кодовой базе, толще миграция, 80% ценности даёт A); C — минимальный мост без изменения моделей (сопоставление по `item_name` хрупко, реквизиты 766н некуда класть).

Карточка — **гибрид** (решение пользователя): храним то, чего требует 766н и что не выводится из журнала (размеры работника, № сертификата, % износа, ссылка на подписанный документ), сама карточка собирается вычисляемым GET-эндпоинтом. Полностью хранимая карточка отвергнута (дублирует журнал выдач, требует синхронизации); чисто вычисляемая — не вмещает реквизиты 766н.

## 3. Данные и миграция `sz01` (аддитивная + конверсия статуса)

Новая миграция `20260610_sz01_ppe_norms_card_766n.py`, `down_revision = "20260610_con02_contractor_document_requirements"` — продолжение линейной цепочки контурных миграций (`iter49 → med01 → con01 → con02 → sz01`), та же конвенция, что у medical/contractors ([[alembic-heads-lesson]]).

### 3.1 `ppenorm` — привязка к каталогу

| Колонка | Тип | Примечание |
|---|---|---|
| `item_id` | String(36), FK → `ppeitem.id` ON DELETE SET NULL, **nullable**, index | Существующие строки (только `item_name`) остаются валидными. Новый CRUD требует `item_id`; `item_name` денормализуется из `PPEItem.name` при создании/смене item. |

Сопоставление «положено-vs-выдано» в карточке: по `item_id`; для legacy-строк нормы без `item_id` — fallback по `item_name` (точное совпадение).

UniqueConstraint `uq_ppe_norm_position_hazard_item(tenant_id, position_id, hazard_id, item_name)` сохраняется как есть (item_name денормализован → дубль по item_id даёт дубль по item_name).

### 3.2 `person` — размеры/антропометрия (766н)

| Колонка | Тип | Примечание |
|---|---|---|
| `ppe_sizes` | JSON, nullable | Ключи: `height` (рост, см), `clothing_size`, `shoe_size`, `headgear_size`, `gas_mask_size`, `respirator_size`, `gloves_size`, `mittens_size`. Все опциональны — состав по 766н зависит от выдаваемых СИЗ. Прецедент JSON-поля: `Person.current_ppe`. |

### 3.3 `ppeissue` — реквизиты 766н + замена

| Колонка | Тип | Примечание |
|---|---|---|
| `certificate_no` | String(255), nullable | № сертификата/декларации соответствия выданного СИЗ |
| `wear_percent` | Integer, nullable | % износа при выдаче (0–100, валидация на API) |
| `return_wear_percent` | Integer, nullable | % износа при возврате |
| `signature_doc_ref` | String(255), nullable | Ссылка на учётный документ с личной подписью работника (электронная форма карточки по 766н). Строка-референс, НЕ FK (анти-грабли cross-base/cross-domain) |
| `writeoff_reason` | String(255), nullable | Основание списания |
| `replaces_issue_id` | String(36), nullable, index | Новая выдача-замена ссылается на закрытую. Строка-референс без FK constraint (self-reference не критичен, дешевле без FK) |

### 3.4 Конверсия `ppeissue.status`: native enum → VARCHAR(32)

- Значения: `issued | returned | written_off | replaced | lost` (lowercase).
- PG: `ALTER COLUMN status TYPE VARCHAR(32) USING lower(status::text)`, затем `DROP TYPE ppeissuestatus`. Существующие данные `'ISSUED'/'RETURNED'/'LOST'` нормализуются lowercase'ом в той же операции.
- SQLite (тестовый контур): batch_alter / пересоздание колонки + `UPDATE ... SET status = lower(status)`.
- ORM: `PPEIssueStatus(str, enum.Enum)` остаётся как **справочник значений** (`.value` lowercase), колонка становится `String(32)`; все записи в код идут через `.value`.
- Downgrade: воссоздать тип `ppeissuestatus` с исходными 3 значениями + UPPER-данные; строки `written_off/replaced` при downgrade маппятся в `RETURNED`/`LOST`? — НЕТ: downgrade честно фейлится, если встречены новые значения (как в [[migration-downgrade-repair]] — асимметрии фиксируются явно); при отсутствии новых значений — обратная конверсия UPPER + restore enum.
- Конвенция: VARCHAR вместо native enum — линия последних контуров (contractors `con01`/`con02`, medical `med01`) после PG-enum инцидентов ([[enum-pg-label-parity]]).

**Затронутые читатели статуса** (перевести на строковые значения/`.value`): `modules/analytics/services.py:130` (`ppe_overdue` + дашборды), `modules/data_quality/rules.py:392` (`ExpiredPPEIssuesRule`), `modules/operational_dashboard/service.py:69` (overdue-alerts), `api/routes/ppe.py` (issue write-path/фильтры), `domains/ppe/service.py` (`list_expiring_issues`, `build_personal_card_payload`), схемы `schemas/ppe.py`.

### 3.5 Что НЕ трогаем в БД

- Таблицы семейства B (`ppe_catalog`, `ppe_norms`, `ppe_norm_items`, `ppe_issues`, `ppe_personal_cards`, `ppe_personal_card_items`) и `warehouseppe` остаются в БД; DROP — отдельная аккуратная миграция вне среза.
- Миграция `20260401_next58_safety_core.py` не редактируется.
- `ppeitem.category` (native enum `ppeitemcategory`) — вне среза.

## 4. Домен `domains/ppe/` (паттерн medical/contractors)

### 4.1 `lifecycle.py` — новый чистый модуль (ноль I/O, ноль sqlalchemy)

```
ISSUE_STATUS_ISSUED = "issued" … ISSUE_STATUS_LOST = "lost"   # константы = PPEIssueStatus.value

ALLOWED_TRANSITIONS = {issued → {returned, written_off, replaced, lost}}
# терминальные: returned/written_off/replaced/lost → ∅

validate_transition(current: str, target: str) -> None | raise PPETransitionError(code, detail)

CardLineStatus: OK | DUE_SOON | OVERDUE | MISSING        # строковые константы

card_line_status(required_qty: int, active_issues: list[IssueView], today: date,
                 due_soon_days: int = 30) -> str
# нет активных выдач → MISSING
# сумма quantity активных < required_qty → MISSING (частичная выдача)
# есть выдача с истёкшим expires_at → OVERDUE
# есть выдача с expires_at в горизонте due_soon_days → DUE_SOON
# иначе OK
# expires_at IS NULL → бессрочно, не влияет на OVERDUE/DUE_SOON
# классификация срока переиспользует domains/shared.classify (паттерн contractors/medical)

fold_card_status(line_statuses: Iterable[str]) -> str
# worst-of: MISSING/OVERDUE → worst, DUE_SOON, OK; пустая карточка (нет норм) → OK
```

`IssueView` — лёгкий протокол/dataclass (quantity, expires_at, status) — lifecycle не знает про ORM.

### 4.2 `service.py` — расширение существующего I/O-сервиса

- `build_personal_card_766n(session, *, tenant_id, person_id) -> PersonalCard766n | None`:
  - Шапка: ФИО, табельные атрибуты, подразделение/должность (из `Person`/`Position`), пол, дата приёма, размеры из `person.ppe_sizes`.
  - «Положено»: нормы по `person.position_id` (все hazard'ы должности), объединение через переиспользуемый `modules/ppe/services.py::PPENormService.required_union` — max количества на позицию каталога; ключ — `item_id` (fallback `item_name` для legacy-норм).
  - «Выдано/возвращено»: все `PPEIssue` работника (не-удалённые), с реквизитами 766н (`certificate_no`, `wear_percent`, `return_wear_percent`, `signature_doc_ref`, `replaces_issue_id`).
  - Статус каждой строки «положено» через `card_line_status`; итог карточки через `fold_card_status`.
  - Timeline: события по датам (issued_at/returned_at/обновления статусов) — derived из issues, без отдельной таблицы.
- Операции жизненного цикла — **as-built: три отдельные функции вместо одной `apply_issue_operation`** (по функции на операцию — проще сигнатуры и возвраты):
  - `return_issue(session, *, tenant_id, issue_id, returned_at=None, return_wear_percent=None, signature_doc_ref=None) -> PPEIssue | None`;
  - `writeoff_issue(session, *, tenant_id, issue_id, reason) -> PPEIssue | None`;
  - `replace_issue(session, *, tenant_id, issue_id, item_id=None, quantity=None, …) -> tuple[PPEIssue, PPEIssue] | None` — старая → `replaced`, новая выдача через существующий `issue_ppe_item` + `replaces_issue_id`; возвращает пару (old, new).
  - Общий контракт: загрузка issue tenant-scoped (`None` → 404 на API), `validate_transition` (`PPETransitionError` → 409). Outbox-события (`PPE_RETURNED` / `PPE_WRITTEN_OFF` / `PPE_ISSUED` для replace) enqueue'ятся не в сервисе, а в эндпоинтах `api/routes/ppe.py` (`return_issue_endpoint` / `writeoff_issue_endpoint` / `replace_issue_endpoint`) — в той же транзакции/сессии запроса.
- `notify_replacement_due(session, *, tenant_id, within_days=30)` — outbox `PPE_REPLACEMENT_DUE`, idempotency_key `ppe-replacement-due:{issue_id}:{status}:{utc_day}` (паттерн `notify_document_expiry` подрядчиков; noop-дедуп починен в Срезе-2 подрядчиков). **As-built:** живёт в `services/ppe_notifications.py` и сам выбирает активные выдачи с `expires_at` (+ `classify` из `domains/shared`); отдельный `list_replacement_due` не понадобился.

## 5. API (роутер `/ppe`, существующие конвенции: `_PPE_READ/WRITE_ROLES`, ABAC `abac(_tenant_resource_id, ...)`, `TenantContextValidator`, `@audit_operation`, структурированные ошибки `_ppe_bad_request`)

| Метод | Путь | Поведение |
|---|---|---|
| GET | `/ppe/norms` | список норм тенанта (фильтр `position_id`, пагинация limit/offset, ETag по паттерну существующих list-эндпоинтов) |
| POST | `/ppe/norms` | создать; `item_id` обязателен, `item_name` денормализуется; 409 `PPE_NORM_DUPLICATE` на (tenant, position, hazard, item); 404 на чужие/несуществующие position/hazard/item |
| GET | `/ppe/norms/{id}` | 404 чужой тенант |
| PATCH | `/ppe/norms/{id}` | quantity/interval_days/item_id (с пере-денормализацией item_name); 409 на дубль |
| DELETE | `/ppe/norms/{id}` | жёсткое удаление (у PPENorm нет SoftDeleteMixin) |
| POST | `/ppe/issues/{id}/return` | body: `returned_at?`, `return_wear_percent?`, `signature_doc_ref?` → статус `returned` + outbox `PPE_RETURNED`; 409 из терминального статуса |
| POST | `/ppe/issues/{id}/writeoff` | body: `writeoff_reason` (обязателен) → `written_off` + outbox `PPE_WRITTEN_OFF`; 409 из терминального |
| POST | `/ppe/issues/{id}/replace` | body: payload новой выдачи (как `PPEIssueCreate` без person_id — берётся из старой) → старая `replaced`, новая `issued` с `replaces_issue_id` + `PPE_ISSUED`; 409 из терминального |
| GET | `/ppe/employees/{person_id}/card` | карточка 766н; 404 несуществующий/чужой person |
| PUT | `/ppe/employees/{person_id}/sizes` | полная замена `ppe_sizes` (PUT-семантика); валидация ключей по белому списку §3.2, height 100–250, размеры — строки ≤16 символов |

Legacy `PATCH /ppe/issues/{id}`: остаётся (фронт `PpePage` им пользуется), но смена `status` проходит `validate_transition` — 409 на невалидный переход. Поля `status` в `PPEIssueUpdate` принимают и новые значения.

Без нового feature-flag: контур `/ppe/*` сейчас не флагован (флаг `warehouse` покрывает только stock) — сохраняем как есть.

## 6. Автоматизация и события

- `EventType.PPE_WRITTEN_OFF = "PPEWrittenOff"` + `PPEWrittenOffPayload (issue_id, person_id, item_name, reason)`.
- `EventType.PPE_REPLACEMENT_DUE = "PPEReplacementDue"` + `PPEReplacementDuePayload (issue_id, person_id, item_name, expires_at)`.
- Beat: `ppe-expiry-daily` → task `ppe.expiry.tick` (04:15 UTC, свободный слот; соседи: contractors-documents 03:45, medical-contingent и т.п.) — атомарный паттерн contractors: по всем тенантам с активными выдачами → `notify_replacement_due`.

## 7. Чистка долга (в этом срезе)

- Удалить из `safety_core.py`: `PPENorm` (safety_core), `PPECatalog`, `PPENormItem`, `PPEIssue` (safety_core), `PPEPersonalCard`, `PPEPersonalCardItem` — минус 2 дубля имён классов ([[orm-duplicate-class-names]]: PPENorm, PPEIssue).
- Удалить `WarehousePPE` из `models.py` + реэкспорты из `ppe_registry.py` и `models/__init__.py`.
- `modules/ppe/services.py` (чистая логика) — **остаётся** и переиспользуется (`required_union`, при необходимости `apply_issue_events`); `test_next58_safety_core_services.py` продолжает проходить (он тестирует чистые сервисы, не ORM).
- Проверить отсутствие прочих импортов удаляемых классов (grep перед удалением); guard-тест `configure_mappers()` должен остаться зелёным.

**As-built — нейтрализация живого читателя семейства B.** Grep выявил один живой read-only потребитель: `GET /packs/{pack_run_id}/safety-summary` (`api/routes/packs.py::pack_safety_summary`) читал `PPEPersonalCard`/`PPEPersonalCardItem` для построения `issued_ppe`. Поскольку write-path к этим таблицам никогда не существовал, чтение всегда давало пустой список (provably dead); `missing_ppe` и до среза был захардкожен `{}`. Чтение семейства B заменено константой `issued_ppe = []` с поясняющим комментарием — контракт ответа эндпоинта сохранён без изменений; реальные личные карточки теперь живут в `GET /ppe/employees/{person_id}/card`.

## 8. Demo-seed (`services/demo_bootstrap.py`)

- 2–3 нормы с `item_id` (существующие demo-PPEItem или создать).
- `ppe_sizes` одному работнику (рост + одежда + обувь).
- Выдачи: одна активная с `certificate_no`, одна просроченная (OVERDUE), одна позиция нормы без выдачи (MISSING) — карточка демонстрирует все статусы.

## 9. Тесты

Раскладка (урок Среза-3 подрядчиков): чистые/герметичные тесты → `backend/tests/`; тесты с БД/API, которым нужны фикстуры `sessionmaker`/`data_factory`, → корневой `tests/`.

| Группа | Где | Что |
|---|---|---|
| lifecycle unit | `backend/tests/test_ppe_lifecycle.py` | FSM: все разрешённые/запрещённые переходы; `card_line_status`: MISSING (нет выдач; частичная), OVERDUE, DUE_SOON, OK, бессрочная; `fold_card_status` worst-of |
| миграция | `backend/tests/test_sz01_ppe_766n_migration.py` | новые колонки; конверсия статуса (lowercase, тип удалён); AST/герметично без route-импортов ([[local-env-drift-windows]]) |
| нормы API | `tests/api/test_ppe_norms_api.py` | CRUD, 409 дубль, tenant-изоляция, 404 чужой position/item, денормализация item_name |
| операции API | `tests/api/test_ppe_issue_operations_api.py` | return/writeoff/replace happy-path + 409 из терминального; outbox-события; legacy PATCH через FSM |
| карточка | `tests/test_ppe_personal_card_766n.py` | шапка+размеры; положено-vs-выдано по item_id + fallback item_name; статусы строк; timeline; 404 |
| sizes API | в `test_ppe_norms_api.py` или отдельно | PUT валидация белого списка, чужой тенант 404 |
| beat/notify | `tests/test_ppe_replacement_due_tick.py` | идемпотентность (дважды → одно событие), горизонт |
| события | `backend/tests/test_ppe_events.py` | payload-схемы новых EventType |
| access parity | расширить `backend/tests/test_ppe_access_parity.py` | write ⊆ read для новых эндпоинтов |
| читатели статуса | прогон существующих analytics/data-quality/operational-dashboard тестов | регрессия конверсии VARCHAR |
| demo-seed | `tests/test_demo_bootstrap_ppe.py` | нормы/размеры/выдачи посеяны |

Прогон локально: Py3.13.7/.venv, `-p no:xdist --timeout=120`, через PowerShell→file ([[py313-win-pytest-invocation]]); канон Py3.12 = CI (выключен, [[ci-disabled-actions-off]]).

## 10. Ошибки и инварианты

- 409 `PPE_TRANSITION_INVALID` — операция из терминального статуса / невалидный переход (и через операции, и через legacy PATCH).
- 409 `PPE_NORM_DUPLICATE` — дубль нормы.
- 404 — чужой тенант (нормы, выдачи, person) — tenant-изоляция как в существующем роутере.
- Карточка не падает на legacy-данных: нормы без `item_id`, выдачи без сертификата, person без размеров → поля null/fallback.
- `wear_percent`/`return_wear_percent` ∈ [0,100].
- Outbox-события — в той же транзакции, что и запись (существующий паттерн роутера).

## 11. Вне среза (Срез-2+)

- Печатная форма карточки (МБ-7/766н-форма) и подпись работника через ЭДО (сейчас — `signature_doc_ref` строкой).
- Сезонность, альтернативы, рекомендованные СИЗ, история изменений норм (§12.1 хвост), ЕТН-структура 767н.
- Склад вглубь: перемещения, резервирование, инвентаризация, поставщики, min/max, прогноз (§12.3).
- Бюджетный контур (§12.4), мобильная выдача (§12.5).
- DROP таблиц семейства B и `warehouseppe`.
- Фронтенд карточки/норм (текущий `PpePage` продолжает работать; PATCH-совместимость сохранена).
- Связь СИЗ-просрочек с гейтом допуска (`person_admission`) — кандидат на следующий срез по образцу медицины.
