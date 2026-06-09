# Подрядчики — Срез 2: реестр документов/сертификатов

- **Дата:** 2026-06-09
- **Контур:** ТЗ раздел B.14 «Подрядчики, посетители, допуск» (`vNext §15`, guided data collection §15.2)
- **Ветка:** `feat/contractors-documents` (от `main`@`27faedc`)
- **Подход:** аддитивно — новая таблица `contractor_documents` + сервис/уведомления + API под существующим роутером `/contractors`, по образцу `TrainingCertificate` и `domains/medical`.
- **Статус:** design approved (брейншторм), pending написание плана реализации.

## 1. Контекст и проблема

Срез 1 (PR #644, влит `27faedc`) построил **движок допуска**: вердикт `ALLOWED/WARNING/BLOCKED` на сотрудника-подрядчика, гейт `POST /contractors/employees/{id}/admit` (409), проекция read-модели, beat `contractors.readiness.tick`, feature-flag `contractors`, demo-seed.

Вердикт читает **ручные статус-флаги** `ContractorEmployee.access_status / training_status / medical_status` + дедлайны `last_training_at / next_medical_at` (`backend/app/modules/contractors/models.py:43-68`). Но **самих документов нет** — нельзя приложить удостоверение об обучении, медицинское заключение, лицензию подрядчика, страховку; нельзя отследить срок действия файла; нельзя ответить «какие документы у этого подрядчика и когда истекают».

Это — отложенный пункт Среза 1 («модель контракторских документов/сертификатов + загрузка»). Срез 2 закрывает его как **самостоятельный реестр документов с реальным потоком** (вычисление срока + уведомления об истечении), не трогая движок допуска.

### Решение пользователя (брейншторм 2026-06-09)
Документы — **отдельный реестр с уведомлениями**, НЕ влияют на вердикт допуска в этом Срезе. Связь «документ → вердикт» (требуемые типы документов гатят допуск) отложена в Срез 3. Мотивация: ноль регрессии для только что влитого движка + ограниченный связный объём.

## 2. Объём (Срез 2)

**В объёме:**
1. Модель `ContractorDocument` (новая таблица `contractor_documents`, аддитивная миграция).
2. Чистая логика срока: `document_expiry_status(valid_until, today) -> ContingentItemStatus` (обёртка над переиспользуемым `classify`).
3. CRUD-API документов под `/contractors/documents` (те же gate/роли/ABAC, что у Среза 1) + advisory `GET /contractors/documents/expiring`.
4. Сервис уведомлений `notify_document_expiry` + ежедневный beat `contractors.documents.tick` + 2 `EventType` (`contractor.document_expiring`, `contractor.document_expired`).
5. Demo-seed: 3 документа (валидный / истекающий / просроченный) для demo-сотрудников.

**Вне объёма (отложено в Срез 3+):**
- Связь «документ → вердикт допуска» (требуемые типы документов как требования допуска) — Срез 3.
- Guided-collection wizard (§15.2 пошаговый сбор) — Срез 3.
- Посетители/гости (visitors) — отдельный под-проект.
- Интеграция реальных доменов medical/training (вывод статусов из `medical_exam`/training-таблиц вместо собственных полей `ContractorEmployee`) — отдельный под-проект.
- FSM-запись допуска (`REQUESTED→GRANTED→…`) + временное окно доступа — отдельный под-проект.
- Бюджет безопасности (§12.4).

## 3. Архитектура и компоненты

### 3.1 Модель `backend/app/modules/contractors/models.py` (+ `ContractorDocument`)
По образцу `TrainingCertificate` (`backend/app/models/models.py:1043-1080`). Базовые классы `TenantBaseModel, SoftDeleteMixin` дают `id`/`tenant_id`/`created_at`/`updated_at`/`version`/`deleted_at`.

| Колонка | Тип | Назначение |
|---|---|---|
| `contractor_id` | `String(36)` FK→`contractor_registry.id` ON DELETE CASCADE, NOT NULL, index | владелец-подрядчик |
| `employee_id` | `String(36)` FK→`contractor_employees.id` ON DELETE SET NULL, nullable, index | если задан — документ сотрудника; null — документ организации |
| `doc_type` | `String(64)`, NOT NULL | тип документа (валидируется на уровне Pydantic-схемы, **не PG-enum**) |
| `title` | `String(255)`, NOT NULL | название |
| `number` | `String(128)`, nullable | номер документа |
| `issuing_org` | `String(255)`, nullable | кем выдан |
| `issued_at` | `Date`, nullable | дата выдачи |
| `valid_until` | `Date`, nullable | срок действия (вход в `classify`) |
| `file_id` | `String(36)`, nullable | ссылка на `File` (app-level, **без cross-base FK**) |
| `status` | `String(32)`, NOT NULL, default `"active"` | `active` / `archived` |

**Индексы:** `(tenant_id, contractor_id)`, `(tenant_id, employee_id)`, `(tenant_id, valid_until)` (скан истечений), `(tenant_id, doc_type)`.

**Два сознательных решения против известных граблей репозитория:**
1. `doc_type` — **`String(64)` + Pydantic-валидация**, а не PG-enum, чтобы не входить заново в «enum-label-parity» сагу (52 колонки чинились серией PR #635–#638). Цена: валидация вокабуляра в схеме, не в БД. Приемлемо для справочного поля.
2. `file_id` — **`String(36)` без DB-FK** (app-level reference), как `contractor_registry.company_id` (`models.py:29`). Cross-base FK уже ломали миграции (wa02 пришлось дропать FK у `FeatureEnablement`); `File` живёт в отдельной metadata-base. Целостность — на уровне приложения.

**Вокабуляр `doc_type`** (валидация в схеме, не в БД):
- организация: `license`, `insurance`, `contract`, `sro`
- сотрудник: `training_cert`, `medical_cert`, `access_permit`, `qualification`
- общий: `other`

Жёсткой привязки «тип → уровень (org/employee)» в этом Срезе нет — гибкость; рекомендованное использование документируется. `employee_id`, если задан, должен принадлежать тому же `contractor_id` (валидация в сервисе/роуте).

### 3.2 Чистая логика срока `backend/app/domains/contractors/documents.py` (новый)
- `document_expiry_status(valid_until: date | None, today: date) -> ContingentItemStatus` — тонкая обёртка над `app.domains.shared.classify`.
- **Отличие от требований допуска:** документ **без** `valid_until` → `OK` (бессрочный/срок неприменим), а не `MISSING`. `MISSING` в `classify` означает «нет даты у обязательного требования»; здесь отсутствие срока — легитимное состояние документа.
- Без I/O, без зависимости на ORM-сессию — тестируется чисто.

### 3.3 Миграция `backend/app/migrations/versions/20260609_con01_contractor_documents.py` (новая, аддитивная)
- `down_revision = "20260607_med01_medical_domain"` (текущий head; подтвердить при написании плана — Срез 1 миграций не добавлял).
- Только `op.create_table("contractor_documents", …)` + 4 индекса. Без enum-типов (doc_type/status — VARCHAR). Без cross-base FK на `file`.
- `downgrade()` — `op.drop_table` + дроп индексов (round-trip-safe; нет осиротевших enum-типов, т.к. enum'ов нет).

### 3.4 API `backend/app/api/routes/contractors.py` (+ document-эндпоинты)
Под существующим роутером `/contractors`, переиспользуя `ReaderAccess`/`WriterAccess`/`ContractorsFeatureGate`/ABAC по `contractor_id`.

- `GET /contractors/documents` — список. Фильтры: `contractor_id`, `employee_id`, `doc_type`, `status`. ABAC `contractor_ids` из claims (как в `list_contractor_employees`). ETag (`compute_list_etag`). Каждая строка отдаёт вычисленный `expiry_status` (из §3.2). ReaderAccess.
- `POST /contractors/documents` — создать. `file_id` опционален → допускается metadata-only запись (файл прикладывается позже, поддержка guided-collection). Валидация: `employee_id` принадлежит `contractor_id`; `doc_type` ∈ вокабуляр. WriterAccess.
- `GET /contractors/documents/{id}` — карточка (с `expiry_status`). ReaderAccess.
- `PATCH /contractors/documents/{id}` — правка (включая `file_id`, `valid_until`, `status`). WriterAccess.
- `DELETE /contractors/documents/{id}` — soft-archive (`deleted_at`). 204. WriterAccess.
- `GET /contractors/documents/expiring` — advisory: документы со `valid_until`, у которых `expiry_status ∈ {DUE_SOON, OVERDUE}`, в пределах окна. ReaderAccess.

**Загрузка файла** — через существующий `POST /files/upload` (`backend/app/api/routes/files.py:504`): клиент загружает файл → получает `file_id` → передаёт его в create/patch документа. Новый multipart-эндпоинт **не делаем** — переиспользуем AV-scan/quarantine пайплайн `File`.

Pydantic-схемы (`ContractorDocumentCreate/Patch`) с `doc_type` как `Literal[...]`/enum-валидацией вокабуляра.

### 3.5 Сервис уведомлений `backend/app/services/contractor_documents.py` (новый)
По образцу `notify_readiness` (`backend/app/services/contractor_admission.py:81`):
- `async def notify_document_expiry(session, *, tenant_id) -> int` — грузит non-deleted документы тенанта со `valid_until is not None`, классифицирует, enqueue outbox:
  - `contractor.document_expiring` для `DUE_SOON`
  - `contractor.document_expired` для `OVERDUE`
  - Идемпотентность per-doc/status/UTC-дата: ключ `contractor-document:{doc_id}:{status}:{today}`.
  - payload: `{tenant_id, metadata: {document_id, contractor_id, employee_id, doc_type, valid_until, status}}`.
- Возвращает счётчик enqueued.

### 3.6 Beat `backend/app/tasks/_core.py` + `backend/app/services/celery_app.py`
- Задача `contractors.documents.tick` (ежедневно, рядом с `contractors.readiness.tick`). **Атомарность:** enqueue → commit в одной транзакции (урок Среза 1 — `31ea873`).

### 3.7 События `backend/app/services/events.py`
- `CONTRACTOR_DOCUMENT_EXPIRING = "contractor.document_expiring"`
- `CONTRACTOR_DOCUMENT_EXPIRED = "contractor.document_expired"`

### 3.8 Demo-seed `backend/app/services/demo_bootstrap.py`
3 документа для существующих demo-сотрудников-подрядчиков:
- валидный (`valid_until` далеко в будущем, `training_cert`)
- истекающий (`valid_until` через ~15 дней, `medical_cert`) → DUE_SOON
- просроченный (`valid_until` в прошлом, `access_permit`) → OVERDUE

## 4. Потоки данных

1. **Регистрация документа:** (опц.) `POST /files/upload` → `file_id`; `POST /contractors/documents` с `contractor_id`/`doc_type`/`file_id`/`valid_until`.
2. **Просмотр:** `GET /contractors/documents?contractor_id=…` → список с `expiry_status` per row; `GET …/expiring` → только истекающие/просроченные.
3. **Уведомления:** ежедневный beat → `notify_document_expiry` per tenant → outbox-события → существующий dispatch (webhooks/нотификации).

## 5. Обработка ошибок и инварианты
- Tenant-isolation: все запросы фильтруют `tenant_id`; cross-tenant id → 404 (как у Среза 1).
- ABAC: `contractor_ids` из claims ограничивают видимость (как `list_contractor_employees`).
- Feature-gate: `contractors` выключен у тенанта → 404 на document-эндпоинтах.
- `employee_id ∉ contractor_id` → 422 (валидация в create/patch).
- `doc_type` вне вокабуляра → 422 (Pydantic).
- Идемпотентность уведомлений: повторный beat в тот же день не дублирует события.
- **Движок допуска, его проекция и read-модель НЕ изменяются** — ноль регрессии Среза 1.

## 6. Тестирование
- **Чистая логика** (`document_expiry_status`): OK без срока, OK/DUE_SOON/OVERDUE по датам, граница окна.
- **API-контракт:** CRUD happy-path; list-фильтры; `expiry_status` в ответе; ETag/304; tenant-isolation (cross-tenant 404); ABAC (`contractor_ids` сужает); feature-gate 404; `employee_id`-mismatch 422; `doc_type`-validation 422; metadata-only (без file_id).
- **Сервис уведомлений:** enqueue для DUE_SOON/OVERDUE, пропуск OK/без-срока, идемпотентность per-день.
- **Миграция:** upgrade создаёт таблицу+индексы; round-trip downgrade чистый.
- **Demo-seed:** 3 документа создаются, статусы корректны.

## 7. Обязательные правила (§E канона)
Аддитивная миграция · feature flag (переиспользуем `contractors`) · tenant isolation на всех границах · события через outbox · тяжёлое (уведомления) в beat-воркере · unit+API тесты · OpenAPI (автоматически) + demo-seed · строгая типизация (backend Pydantic + ORM).

## 8. Acceptance
- Таблица `contractor_documents` + миграция (additive, round-trip-safe) + CRUD-API + expiring-endpoint работают end-to-end.
- ETag на list; tenant-isolation и ABAC покрыты тестами.
- Уведомления об истечении (beat + outbox, идемпотентные) работают.
- Demo-seed с тремя статусами.
- Движок допуска Среза 1 не затронут (регрессий нет).
- Чистая логика срока + API + сервис + миграция + seed зелёные локально (Py3.13.7/.venv; канон Py3.12 = CI).
