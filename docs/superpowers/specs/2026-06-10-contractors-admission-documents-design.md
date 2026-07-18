# Подрядчики Срез-3 — связь «документ → вердикт допуска» (design)

**Дата:** 2026-06-10
**Контур:** ТЗ B.14 «Подрядчики/Допуск», §15 (guided-collection упомянут в §15.2)
**Предшественники:** Срез-1 «движок допуска» (PR #644, `27faedc`), Срез-2 «реестр документов» (ветка `feat/contractors-documents`, 12 коммитов, влита локально-evidence)
**Объём этого среза:** backend-движок гатинга + checklist-API. **Wizard-UI отложен** (отдельный React/Vite-репозиторий).

---

## 0. Проблема и цель

После Срез-2 у подрядчика есть **standalone-реестр документов** (`ContractorDocument`): contractor-уровень
(`employee_id IS NULL`) или employee-уровень, 9 типов (`doc_type` VARCHAR), `valid_until`, классификатор
истечения `document_expiry_status` (нет срока → OK). Но документы **намеренно не влияют** на вердикт допуска —
это и есть пропуск, который закрывает Срез-3.

Движок допуска (`app/domains/contractors/lifecycle.py:evaluate_employee`) сейчас сворачивает **три измерения** —
`access` / `training` / `medical` — каждое через `_assess(status_flag, deadline)`: блок при `EXPIRED/BLOCKED`-флаге
**или** `OVERDUE/MISSING`-дедлайне, warning при `PENDING`/`DUE_SOON`. Вердикт: `BLOCKED` (violations) / `WARNING`
(warnings) / `ALLOWED`.

**Цель Срез-3:** добавить **четвёртое измерение — `documents`** — так, чтобы конфигурируемый набор
«требуемых типов документов» гатил допуск: отсутствующий или просроченный обязательный документ → `BLOCKED`.

---

## 1. Решения дизайна (зафиксированы в brainstorming)

1. **Объём:** только backend-движок гатинга + checklist-API; wizard-UI отложен.
2. **Гранулярность конфигурации:** тенант-политика; каждое правило несёт `scope` (`company` | `employee`).
3. **Серьёзность:** флаг `mandatory` на правило (true → missing/expired = BLOCKED; false → WARNING).
4. **Интеграция движка:** Подход A — расширить чистый `evaluate_employee` + session-aware загрузчик; все
   I/O-пути идут через него (один источник истины для статуса + per-`doc_type` детализация для checklist).

---

## 2. Модель данных

### 2.1. Новая таблица `contractor_document_requirement`

`ContractorDocumentRequirement(TenantBaseModel, SoftDeleteMixin)` в
`backend/app/modules/contractors/models.py`:

| колонка | тип | nullable | смысл |
|---|---|---|---|
| `doc_type` | `String(64)` | no | один из 9-вокабуляра (валидируется на схеме, **не** PG-enum) |
| `scope` | `String(16)` | no | `company` \| `employee` — где искать удовлетворяющий документ |
| `mandatory` | `Boolean`, server_default true | no | true → missing/expired = BLOCKED; false → WARNING |

(`id`, `tenant_id`, `created_at`, `updated_at`, `deleted_at` — из миксинов.)

**Индексы / ограничения:**
- `ix_contractor_doc_req_tenant_type` на `(tenant_id, doc_type)`;
- уникальность `(tenant_id, doc_type, scope)` среди не-удалённых строк. Реализация: на SQLite/PG —
  обычный partial-unique индекс `WHERE deleted_at IS NULL` (зеркало конвенций репо; если partial-unique
  недоступен на целевом диалекте — обеспечить уникальность на сервис-слое перед insert, тест на 409-дубль).

**Анти-грабли контура (сознательно):** `doc_type`/`scope` — VARCHAR, не PG-enum (вне саги label-parity
#635–#638); нет cross-base FK (только `tenant_id`); миграция аддитивная; soft-delete как у соседей.

### 2.2. Удовлетворение требования (без новых колонок на `ContractorDocument`)

«Company-level документ» = `ContractorDocument` с `employee_id IS NULL` у того же подрядчика;
«employee-level» = `employee_id == emp.id`. Отдельная колонка `scope` на документе **не нужна** — это
естественное чтение модели Срез-2. Кандидаты на удовлетворение:

- `scope=company`  → `contractor_id == emp.contractor_id AND employee_id IS NULL AND doc_type == req.doc_type AND status='active' AND deleted_at IS NULL`
- `scope=employee` → `employee_id == emp.id AND doc_type == req.doc_type AND status='active' AND deleted_at IS NULL`

---

## 3. Чистый движок (no-I/O)

### 3.1. `app/domains/contractors/documents.py` — новая pure-функция

```python
def requirement_status(candidates: Sequence[DocLike], today: date) -> ContingentItemStatus:
    """Лучший статус среди документов-кандидатов одного типа/scope.
    Нет кандидатов → MISSING. Иначе best() из document_expiry_status каждого,
    порядок предпочтения OK > DUE_SOON > OVERDUE (open-ended valid_until=None → OK)."""
```

`DocLike` — duck-typed объект с `.valid_until` (как уже делает `evaluate_employee` с `emp`). Переиспользует
`document_expiry_status` Срез-2 → единый источник правды по срокам. `MISSING` появляется **только** здесь
(нет документа вообще), `document_expiry_status` его не возвращает.

«Best» — приоритет `OK > DUE_SOON > OVERDUE`: если хоть один кандидат OK → требование удовлетворено; иначе
если есть DUE_SOON → due_soon; иначе (все просрочены) → overdue.

### 3.2. `app/domains/contractors/lifecycle.py` — расширение `evaluate_employee`

```python
@dataclass
class DocumentRequirement:
    doc_type: str
    scope: str        # "company" | "employee"
    mandatory: bool

def evaluate_employee(
    emp, today, *,
    requirements: Sequence[DocumentRequirement] = (),
    employee_docs: Sequence[DocLike] = (),
    company_docs: Sequence[DocLike] = (),
) -> EmployeeVerdict: ...
```

Новые параметры **опциональны** (default пусто → измерения документов нет → существующие 3-dim unit-тесты
**не меняются**). Для каждого требования:

1. кандидаты = `company_docs` если `scope==company` иначе `employee_docs`, отфильтрованные по `doc_type`;
2. `st = requirement_status(кандидаты, today)`;
3. свёртка (зеркало `_assess`), метка нарушения/предупреждения — `f"document:{doc_type}"`:

| `st` | `mandatory=true` | `mandatory=false` |
|---|---|---|
| `MISSING` / `OVERDUE` | violation → **BLOCKED** | warning |
| `DUE_SOON` | warning → **WARNING** | warning |
| `OK` | — | — |

Итоговый статус employee — как сейчас: есть violations → BLOCKED, иначе warnings → WARNING, иначе ALLOWED.

> **NB по фильтрации:** фильтрацию `status='active'`/`deleted_at IS NULL` делает **сервис-слой** (передаёт уже
> только активные документы). Чистая функция фильтрует только по `doc_type` и считает срок — остаётся pure.

---

## 4. Сервис-слой (`app/services/contractor_admission.py`)

Новый загрузчик — **единственный** канонический путь вычисления вердикта с документами:

```python
async def evaluate_with_documents(
    session, *, tenant_id: str, employees: list[ContractorEmployee],
) -> list[EmployeeVerdict]:
    # 1 запрос: активные requirements тенанта
    # 1 запрос: активные документы — employee-level для переданных emp.id
    #           + company-level (employee_id IS NULL) их contractor_id
    # split company/employee по contractor_id → lifecycle.evaluate_employee(... requirements, docs)
```

- `enforce_contractor_admission` и `notify_readiness` переводятся на `evaluate_with_documents` (вместо
  текущего pure `evaluate_contractor_admission`). Сохраняются: `employees_not_found`-guard,
  `requirements_not_met`-raise, идемпотентность outbox-ключа.
- `evaluate_contractor_admission(*, employees)` (pure, 3-dim) **остаётся** как примитив, но прямые вызовы в
  проекции/эндпоинтах заменяются на doc-aware путь (чтобы не было двух способов считать статус).
- **Уведомления:** новых `EventType` нет. Документные нарушения уже сворачиваются в `readiness_blocked`/
  `readiness_warning` (их payload `violations`/`warnings` теперь содержит `document:*`); per-документное
  истечение покрыто `notify_document_expiry` (Срез-2).

---

## 5. API (`app/api/routes/contractors.py`)

Все — под `ContractorsFeatureGate`, ABAC по `contractor_id`, tenant-изоляция, как у соседей.

| метод / путь | доступ | назначение |
|---|---|---|
| `GET /contractors/document-requirements` | Reader | список политики тенанта (ETag как у списков) |
| `POST /contractors/document-requirements` | Writer/admin | `{doc_type: DocType, scope: "company"\|"employee", mandatory: bool=true}`; **409** на дубль `(doc_type,scope)` |
| `DELETE /contractors/document-requirements/{id}` | admin | soft-delete |
| `GET /contractors/employees/{employee_id}/document-checklist` | Reader | **deliverable для wizard'а** (см. ниже) |

`/admit` и `/readiness` — без изменений сигнатуры, но внутри теперь через `evaluate_with_documents`:
вердикт и `409`-`details` могут включать `document:<type>`-violations.

**Тело checklist** (`GET …/document-checklist`):
```json
{
  "employee_id": "...",
  "items": [
    {"doc_type": "medical_cert", "scope": "employee", "mandatory": true,
     "status": "ok|due_soon|overdue|missing",
     "satisfied_by": {"document_id": "...", "valid_until": "2026-09-01"}  /* или null */}
  ]
}
```
Один элемент на каждое активное требование тенанта; `satisfied_by` — лучший (наиболее-OK) удовлетворяющий
документ, либо `null` при `missing`.

**Схемы** (Pydantic, проектный `BaseModel`/`BaseSchema` как у соседних в файле):
`DocumentRequirementCreate` (переиспользует существующий `DocType = Literal[...]`, `Scope = Literal["company","employee"]`),
`DocumentRequirementRead`, `ChecklistItem`/`ChecklistResponse`.

---

## 6. Проекция read-модели

`ContractorReadinessProjectionService.rebuild` (`app/modules/projections/services.py`):

- грузит requirements тенанта + документы один раз, прокидывает в вычисление вердиктов
  (через `evaluate_with_documents` или эквивалентную in-memory свёртку с уже загруженными документами);
- заменяет заглушку `row.missing_docs_count = 0  # … (Срез 2)` (строка ~189) на
  `missing_docs_count = Σ по вердиктам числа violations с префиксом "document:"`;
- `overdue_items_count = Σ len(violations)` — включает документные нарушения автоматически (имя колонки
  шире буквального смысла, см. NB Срез-1).

Без изменений схемы read-модели — колонка `missing_docs_count` уже существует (`next61`).

---

## 7. Миграция

`backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py`:
- `revision = "20260610_con02_contractor_document_requirements"`,
  `down_revision = "20260609_con01_contractor_documents"` (миграция Срез-2);
- `upgrade`: `create_table('contractor_document_requirement', …)` + индексы (+ partial-unique);
- `downgrade`: симметрично (`drop_index` **до** `drop_table`, round-trip-safe — урок downgrade-репары PR #639);
- аддитивная, никаких изменений существующих таблиц.

---

## 8. Demo-seed

`demo_bootstrap` — добавить 2 правила тенанта-демо:
- `sro` / `company` / `mandatory=true`,
- `medical_cert` / `employee` / `mandatory=true`,

чтобы демо-вердикты показывали реальный гатинг (готовый Иван имеет документы → ALLOWED; кто-то без
`medical_cert` → BLOCKED с `document:medical_cert`).

---

## 9. Тестирование (TDD, каждая задача: implementer + spec-review + code-quality-review)

**Pure:**
- `requirement_status`: нет кандидатов→MISSING; open-ended→OK; future→OK; within-window→DUE_SOON;
  past→OVERDUE; best-of-multiple (валидный перекрывает просроченный).
- `evaluate_employee` с документами: mandatory+missing→BLOCKED; mandatory+overdue→BLOCKED;
  non-mandatory+missing→WARNING; due_soon→WARNING; scope-routing (company-док не удовлетворяет
  employee-требование и наоборот); пустые requirements→прежний 3-dim вердикт (back-compat).

**Migration:** con02 upgrade создаёт таблицу/индексы; downgrade-base→re-upgrade round-trip (на доступном
диалекте); дубль `(tenant,doc_type,scope)` отклоняется.

**API:** requirements CRUD (ABAC deny-first, tenant-iso, feature-gate, 409-дубль); checklist (статусы,
`satisfied_by`); `/admit` 409 с `document:<type>`; `/admit` 200 когда комплект собран; cross-tenant.

**Service:** `evaluate_with_documents` — tenant-изоляция, company vs employee разбиение, лучший документ.

**Projection:** `missing_docs_count` наполняется; `overdue_items_count` включает документные.

**Регрессия:** существующий 3-dim когорт (lifecycle/access/deny) + outbox-dispatch — зелёные без изменений.

---

## 10. Безопасностный инвариант (e2e через HTTP)

Активное `mandatory`-требование без удовлетворяющего активного документа (или с просроченным) →
`evaluate_with_documents` → вердикт `BLOCKED` → `POST /contractors/employees/{id}/admit` =
**409 `requirements_not_met`** с `document:<type>` в `details`. Tenant-изоляция и ABAC по `contractor_id`
сохранены. Документы наконец гатят допуск.

---

## 11. Отложено (Срез-4+)

- Wizard-UI guided-collection (§15.2) — фронтенд, отдельный репозиторий.
- Привязка требований к виду работ/риску (height/hot-work) — нет сущности work-type.
- Per-contractor override тенант-политики.
- Посетители/гости; FSM-запись допуска (`REQUESTED→GRANTED→…`) + временное окно; бюджет §12.4.
- Интеграция реальных доменов medical/training как источника документов (сейчас документы независимы).
