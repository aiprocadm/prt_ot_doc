# Подрядчики — Срез 1: движок допуска (admission engine)

- **Дата:** 2026-06-08
- **Контур:** ТЗ раздел B.14 «Подрядчики, посетители, допуск» (`vNext §15`)
- **Ветка:** `feat/contractors-admission-engine` (от `main`@`8158f01`)
- **Подход:** Вариант А — новый домен `domains/contractors/` по образцу `domains/medical/`, аддитивно поверх существующих моделей/CRUD.
- **Статус:** design approved (брейншторм), pending написание плана реализации.

## 1. Контекст и проблема

Контур подрядчиков уже имеет богатый слой данных и CRUD, но **движок допуска — заглушка** («schema theater»):

- Модели есть: `ContractorRegistry` / `ContractorEmployee` / `ContractorIncident` (`backend/app/modules/contractors/models.py:26-91`). У `ContractorEmployee` есть `access_status` / `training_status` / `medical_status` (enum `ComplianceStatus`: `valid/pending/expired/blocked`) + дедлайны `last_training_at`, `next_medical_at`.
- CRUD-API есть: `backend/app/api/routes/contractors.py:95-329` (registry/employees/incidents/compliance-summary).
- **Read-модель уже содержит правильные колонки** под реальный движок: `ContractorReadinessReadModel` (`backend/app/modules/projections/models.py:104-119`) — `workers_total`, `workers_ready`, `missing_training_count`, `overdue_items_count`, `active_packages_count`.
- **Но движок фейковый:** `ContractorReadinessProjectionService.rebuild()` (`backend/app/modules/projections/services.py:106-133`) только считает `ClientPackageRun` и ставит `readiness_status = "warning" if packages_count else "unknown"`. Колонки `workers_*` / `*_count` **никогда не заполняются**. Статусы сотрудников и дедлайны **не проверяются**.

Главная дыра: ручной статус-флаг (`medical_status = valid`) не сверяется с фактическим дедлайном (`next_medical_at` в прошлом) → «протухший VALID» проходит как готовый.

## 2. Объём (Срез 1)

**В объёме:**
1. Настоящий движок готовности: вердикт `ALLOWED` / `WARNING` / `BLOCKED` на сотрудника, с перекрёстной сверкой статус-флага и дедлайна.
2. Жёсткий гейт допуска (enforcing) с контрактом ошибки `requirements_not_met` (байт-в-байт как medical).
3. Переписать `rebuild()` проекции: наполнять реальные колонки read-модели из вердиктов.
4. Ежедневный beat `contractors.readiness.tick` + outbox-события предупреждений/блокировок.
5. Feature-flag `contractors` (default-ON) + демо-seed (готовый и неготовый сотрудник).

**Вне объёма (отложено):**
- Модель контракторских документов/сертификатов и загрузка файлов — Срез 2.
- Посетители/гости (visitors) — Срез 2.
- Lifecycle-запись допуска с FSM (`REQUESTED→GRANTED→ACTIVE→REVOKED→EXPIRED`) + таблица — Срез 2 (Вариант C).
- Интеграция с реальными доменами medical/training (вывод статусов из `medical_exam`/training-таблиц) — Срез 2; в Срезе 1 источник истины = собственные поля `ContractorEmployee`.
- Миграция БД — **не требуется** (модели и колонки read-модели уже существуют).

## 3. Архитектура и компоненты

### 3.1 `backend/app/domains/shared.py` (новый — целевой мини-рефакторинг)
Поднять сюда из `domains/medical/lifecycle.py`:
- enum `ContingentItemStatus` (`OK/DUE_SOON/OVERDUE/MISSING`)
- `classify(latest_valid_until: date | None, today: date, warning_days=30) -> ContingentItemStatus`

`domains/medical/lifecycle.py` начинает импортировать их из shared и **ре-экспортирует** (`from app.domains.shared import classify, ContingentItemStatus`) — обратная совместимость, существующие импорты medical не ломаются. Контур подрядчиков импортирует из shared, без зависимости на medical.

### 3.2 `backend/app/domains/contractors/lifecycle.py` (новый — чистые функции, без I/O)
- `TRAINING_INTERVAL_DAYS = 365` — константа правила (срок годности обучения; не колонка БД).
- enum `ReadinessStatus` (`ALLOWED` / `WARNING` / `BLOCKED`).
- dataclass `EmployeeVerdict(employee_id, status: ReadinessStatus, violations: list[str], warnings: list[str])`.
- `evaluate_employee(emp, today: date) -> EmployeeVerdict` — правила §4.
- Приведение типов: дедлайны `datetime(tz)` → `date` на входе в `classify()`.

### 3.3 `backend/app/services/contractor_admission.py` (новый — зеркало `services/person_admission.py`)
- `evaluate_contractor_admission(session, *, tenant_scope, employees) -> list[EmployeeVerdict]` — чистый расчёт, **без** исключения. Используется проекцией/чтением.
- `enforce_contractor_admission(session, *, tenant_scope, employee_ids) -> None` — грузит сотрудников в скоупе тенанта, считает вердикты; если есть `BLOCKED` — поднимает
  `ValueError({"code": "requirements_not_met", "details": [{"employee_id": "...", "violations": [...]}]})`
  (форма зеркалит `person_admission`, где ключ был `person_id`).

## 4. Правила вердикта

Для каждого сотрудника вычисляются три «требования»:

| Требование | Статус-флаг | Дедлайн (классификация) |
|---|---|---|
| `access` | `access_status` | — (дедлайна нет) |
| `training` | `training_status` | `classify(last_training_at + TRAINING_INTERVAL_DAYS)` |
| `medical` | `medical_status` | `classify(next_medical_at)` |

Свод требования в исход:
- **violation (→ BLOCKED-вклад):** статус ∈ {`EXPIRED`, `BLOCKED`} **или** дедлайн ∈ {`OVERDUE`, `MISSING`}.
- **warning (→ WARNING-вклад):** статус == `PENDING` **или** дедлайн == `DUE_SOON`.
- иначе требование OK.

Итог сотрудника:
- `BLOCKED`, если есть хотя бы одно violation;
- иначе `WARNING`, если есть хотя бы одно warning;
- иначе `ALLOWED`.

`violations` / `warnings` в вердикте — список имён требований (`"access"` / `"training"` / `"medical"`), при желании с суффиксом причины (`"medical:overdue"`). Это даёт UI и outbox-событиям человекочитаемую причину.

> Смысл «настоящего движка»: даже при `medical_status = valid`, если `next_medical_at < today`, требование = violation → сотрудник BLOCKED. Заглушка это пропускала.

## 5. Гейт допуска (API)

Добавляется в `backend/app/api/routes/contractors.py`:

- `POST /contractors/employees/{employee_id}/admit` — enforcing.
  - Готов → `200`, тело: вердикт (`status=allowed`, пустые violations); запись `AuditService` событие `contractor_admission_granted`.
  - Не готов → `422` `requirements_not_met` + детали (через существующий обработчик `ValueError`→422, как у medical).
  - RBAC: write-роли (`admin`, `owner`, `hse_head`) — как существующий write-набор контура.
- `GET /contractors/employees/{employee_id}/readiness` — advisory.
  - `200`, тело: вердикт без enforcement (для карточки сотрудника в UI). RBAC: read-набор контура.

Контракт ошибки идентичен medical → единый обработчик на фронте.

## 6. Read-side (переписать заглушку)

`ContractorReadinessProjectionService.rebuild()` (`projections/services.py:106-133`):
- Для каждого подрядчика тенанта загрузить его `ContractorEmployee` (не soft-deleted).
- Через `evaluate_contractor_admission` получить вердикты.
- Наполнить **существующие** колонки `ContractorReadinessReadModel`:
  - `workers_total` = число сотрудников;
  - `workers_ready` = число `ALLOWED`;
  - `missing_training_count` = число с training-требованием = MISSING;
  - `overdue_items_count` = суммарное число OVERDUE-требований;
  - `readiness_status` = `blocked`, если есть хотя бы один BLOCKED-сотрудник; иначе `warning`, если есть WARNING; иначе `ready`. (Точный строковый словарь выровнять со смежными read-моделями `PersonComplianceReadModel`/`SiteSafetyReadModel` на этапе реализации — если там используется иное значение для «готов», взять его.)
- `active_packages_count` **сохранить** как было (отдельный проход по `ClientPackageRun`), чтобы не ломать существующих потребителей.

## 7. Автоматизация (celery beat)

- Задача `contractors.readiness.tick` (ежедневно ~03:30, рядом с `medical.contingent.tick` в `backend/app/services/celery_app.py:56-73`):
  - пересчёт проекции (`rebuild`) по тенантам;
  - эмит outbox-событий: `CONTRACTOR_READINESS_WARNING` (для DUE_SOON / PENDING) и `CONTRACTOR_READINESS_BLOCKED` (для OVERDUE / MISSING / EXPIRED / BLOCKED).
- Идемпотентность: `rebuild` идемпотентен (upsert read-модели); outbox-события дедуплицируются по ключу `(employee_id, requirement, due_basis_date)`.

## 8. Feature-flag и seed

- Новый `Feature` code `contractors`, title «Подрядчики», default-ON; seed в `backend/app/services/demo_bootstrap.py` (рядом с `medical`).
- Демо-данные: один подрядчик с двумя сотрудниками — один полностью готовый (`ALLOWED`), один с просроченным `next_medical_at` при `medical_status=valid` (демонстрирует ловлю «протухшего VALID» → `BLOCKED`).
- Гейт/эндпоинты за проверкой `is_feature_enabled("contractors", tenant_id)` (как medical).

## 9. Обработка ошибок

- `requirements_not_met` — контракт байт-в-байт medical.
- FSM-перехода/`InvalidTransition` в Срезе 1 нет (нет lifecycle-записи допуска).
- Beat: ошибки на тенант изолируются (один упавший тенант не валит остальных); пересчёт идемпотентен → повтор безопасен.

## 10. Тестирование (по образцу 53 medical-тестов)

- **Юнит `lifecycle`** (app-free, чистые функции): таблица `статус × дедлайн → вердикт`, включая кейс «протухший VALID» → BLOCKED, MISSING-дедлайны, DUE_SOON → WARNING.
- **Юнит `shared.classify`**: лифт не изменил поведение (параметризованные кейсы missing/overdue/due_soon/ok).
- **Сервис** (seeded подрядчики): `evaluate` для всех трёх исходов; `enforce` поднимает `requirements_not_met` с корректными `employee_id`/`violations`.
- **API e2e**: `admit` → `422` для неготового, `200` для готового; `readiness` advisory отдаёт вердикт.
- **Проекция**: `rebuild` наполняет `workers_total/workers_ready/missing_training_count/overdue_items_count` реальными значениями (а не нулями) и корректный `readiness_status`.
- **Регрессии**: существующие тесты `contractors`/`projections` зелёные; импорты `medical` после лифта `classify()` не сломаны (`test_orm_mapper_configuration` + medical-юниты зелёные).

## 11. Манифест файлов

**Новые:**
- `backend/app/domains/shared.py`
- `backend/app/domains/contractors/__init__.py`
- `backend/app/domains/contractors/lifecycle.py`
- `backend/app/services/contractor_admission.py`
- тесты: `backend/tests/test_contractors_lifecycle.py`, `backend/tests/test_domains_shared_classify.py`, `tests/api/test_contractors_admission_api.py`, `tests/test_contractor_readiness_projection.py` (точные пути уточнит план)

**Изменяемые:**
- `backend/app/domains/medical/lifecycle.py` (импорт+ре-экспорт `classify`/`ContingentItemStatus` из shared)
- `backend/app/api/routes/contractors.py` (+2 эндпоинта)
- `backend/app/modules/projections/services.py` (переписать `rebuild`)
- `backend/app/services/celery_app.py` (+beat-задача)
- `backend/app/services/tasks.py` или соответствующий celery-таск-модуль (тело `contractors.readiness.tick`)
- `backend/app/services/demo_bootstrap.py` (feature + seed)

## 12. Последовательность сборки (фазы для плана)

1. `domains/shared.py` — лифт `classify`/`ContingentItemStatus`; medical ре-экспорт; зелёные medical-юниты (рефакторинг без смены поведения).
2. `domains/contractors/lifecycle.py` — `ReadinessStatus`, `evaluate_employee`, правила §4 + юнит-тесты (TDD).
3. `services/contractor_admission.py` — `evaluate`/`enforce` + сервис-тесты.
4. API — `admit` (enforcing) + `readiness` (advisory) + e2e-тесты.
5. Проекция — переписать `rebuild`, наполнить колонки + тест.
6. Автоматизация — beat `contractors.readiness.tick` + outbox-события + идемпотентность.
7. Feature-flag `contractors` + demo-seed (готовый/неготовый сотрудник).
8. Регрессии + holistic-review.
