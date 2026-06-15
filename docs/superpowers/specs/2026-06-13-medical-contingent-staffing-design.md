# Медосмотры §9.2: авто-контингент из штатки + документы 29н — дизайн

**Дата:** 2026-06-13
**Контур:** Медосмотры (ТЗ раздел B.8, vNext §9.2 «Автоматизация: формирование контингента, влияние СОУТ/рисков»)
**Ветка:** `feat/medical-contingent-staffing`
**Статус до среза:** Медосмотры Срез-1 ВЛИТ (PR #643 → `ced6570`). Уже построено из буквального текста §9.2: `compute_contingent` (norm-driven), влияние СОУТ через `resolve_required_kinds` (position.hazards + working_conditions_class), события календаря, блокировка допуска при противопоказании (suspension → admission block). Реально отложенный объём — **авто-контингент из штатного расписания** и **формальные документы приказа 29н**.
**Статус после среза:** ✅ РЕАЛИЗОВАНО И ВЛИТО — PR #651 (`71e3587`). Построены: модель `MedicalFactor` + миграция `med02`, чистый движок (`factors_for_hazards`, `required_exams_from_factors`, factor-driven путь в `compute_contingent`), документы 29н (`build_contingent_register`, `build_named_list`), CRUD `/medical/factors`, эндпоинты `/medical/contingent/register` и `/medical/named-list`, demo-seed, тесты. Проверено аудитом кода 2026-06-15.

## 1. Цель среза

Срез-1 даёт *вычисляемый* контингент, но только для тех, у кого `position_id` проставлен вручную **И** существует подходящая `MedicalNorm`. Формальные артефакты приказа Минздрава № 29н (от 28.01.2021) — **контингент** (перечень профессий/факторов + численность, направляется в Роспотребнадзор) и **поименный список** (конкретные ФИО + должность + факторы + подразделение, направляется в медорганизацию) — не формируются.

Цель: **и движок, и документы**.

1. **Движок** — резолв требуемых осмотров из штатного расписания (должности × вредные факторы 29н) автоматически, без ручного создания `MedicalNorm` на каждую пару. Норма остаётся опциональным override.
2. **Документы** — два формальных артефакта 29н, **вычисляемых на лету** (зеркало личной карточки 766н СИЗ): контингент и поименный список.

Источник «штатного расписания» — **существующие `Position` + `Person`** (должности с hazards/классом УТ; сотрудники с `position_id`/`workplace_id`). Полный импорт штатки/оргструктуры — отдельный vNext §11.3, в этом срезе **не трогаем**.

### Не-цели (отложено, Срез-3+)
- Печатные формы документов «контингент»/«поименный список» (PDF/DOCX).
- Снапшоты/версии документов для отправки в Роспотребнадзор/медорганизацию (в срезе — live-compute, без персистентной таблицы).
- §9.1 — бюджет медосмотров, договоры с медорганизациями.
- §9.3 — health-контур (предсменные/транспортные осмотры).
- §11.3 — загрузка штатки, импорт оргструктуры, автогенерация перечней из внешних источников.
- Полный 29н-справочник «из коробки» (в срезе — модель + CRUD + demo-seed нескольких факторов; наполнение — операционная задача тенанта).

## 2. Архитектура

Три слоя поверх существующего `backend/app/domains/medical/` (Срез-1): данные → чистый движок → документы/API.

### 2.1 Чистые функции — `domains/medical/lifecycle.py`

По образцу существующих `resolve_required_kinds` / `classify` (без I/O):

- `factors_for_hazards(hazard_codes: set[str], catalog: Iterable[FactorTuple]) -> set[FactorTuple]` — отбор 29н-факторов, на которые замаплены коды hazards должности.
- `required_exams_from_factors(factors: Iterable[FactorTuple]) -> dict[MedicalExamKind, int]` — объединение мандатируемых видов осмотра; при конфликте периодичности берётся **строжайшая** (минимальная `periodicity_months`).

`FactorTuple` — лёгкий неизменяемый кортеж `(code, name, exam_kinds, periodicity_months)`, чтобы движок не зависел от ORM.

### 2.2 Расширение `compute_contingent` — `service.py`

Требуемые виды осмотра для сотрудника = объединение двух путей:
1. **norm-driven** (как есть в Срез-1): `resolve_required_kinds(position_id, working_conditions_class, hazard_ids, norms)`.
2. **factor-driven** (новый): `required_exams_from_factors(factors_for_hazards(position_hazard_codes, factor_catalog))`.

Периодичность для классификации: из `MedicalNorm.interval_days`, если норма есть; иначе `interval_days = periodicity_months × 30` фактора (документированная аппроксимация — переиспользует существующую day-based `compute_valid_until`/`interval_for_kind` Среза-1, не вводя месячную арифметику). Классификация против последнего осмотра — прежняя `classify` (ok/due_soon/overdue/missing).

**Эффект:** сотрудник попадает в контингент даже без ручной нормы — достаточно, чтобы у его должности были hazards, замапленные на 29н-факторы. **Back-compat сохранён** — норм-путь не изменяется, существующие тесты Среза-1 зелёные.

### 2.3 Сервисы документов — `service.py` (live-compute, без снапшот-таблицы)

- `build_contingent_register(session, tenant_id, today) -> list[dict]` — строки уровня должности: `{position_id, position_name, factors: [{code, name}], headcount, exam_kinds, periodicity_months}`. `headcount` = число активных (не удалённых, `employment_status=active`) `Person` в должности. Включаются должности с вредными факторами и `headcount > 0`.
- `build_named_list(session, tenant_id, today) -> list[dict]` — строки уровня сотрудника: `{person_id, full_name, position_name, department, factors: [{code, name}], last_exam_date, next_due_date, status}`. `department` — из `workplace`/`site` при наличии, иначе None. Переиспользует `compute_valid_until`/`classify`.

Оба сервиса делят общий загрузчик факторов (каталог + маппинг hazard→factor), чтобы движок и документы давали одну семантику по построению.

## 3. Данные — миграция `med02`

`20260613_med02_medical_factor_catalog` (цепочка `… → ed03 → med02`, голова цепочки на момент написания — `20260612_ed03_briefing_signature_unique`).

### 3.1 Новая таблица `medical_factor` (tenant-scoped)

| Колонка | Тип | Назначение |
|---|---|---|
| `id` | String(36), PK | UUID |
| `tenant_id` | (как у прочих TenantBaseModel) | арендатор |
| `code` | String(32), NOT NULL | пункт 29н, напр. «4.4», «1.1», «6.1» |
| `name` | String, NOT NULL | наименование фактора/вида работ |
| `category` | String(16), NOT NULL | `factor` \| `work` (**VARCHAR, не PG-enum** — анти-грабля enum-label-parity) |
| `exam_kinds` | JSON, NOT NULL | список `MedicalExamKind` |
| `periodicity_months` | Integer, NOT NULL, default 12 | периодичность |
| `participants` | JSON, nullable | специалисты (детализация документа) |
| `lab_tests` | JSON, nullable | лаб/функц. исследования |
| `created_at`/`updated_at` | (как у прочих) | аудит |

**Unique:** `(tenant_id, code)`.

### 3.2 Колонка привязки

`risk_hazards.medical_factor_code` — `String(32), nullable`, **без cross-base FK** (анти-грабля: cross-base FK ломали wa02; зеркало `contractor.file_id`/`contractor_registry.company_id`). Маппит тенант-риск (`RiskHazard.code`) → код 29н-фактора.

### 3.3 Downgrade

Честный: `DROP TABLE medical_factor` + `DROP COLUMN risk_hazards.medical_factor_code`. Round-trip-safe. Guard-тест по образцу `sz02`/`ed02` (пинит цепочку, состав таблицы/колонки, FK-отсутствие).

> **Анти-грабля (повторно):** AST-аудит ORM↔миграций не видит `op.add_column`/таблицы через модульную константу `TABLE` — имена писать **литералом** ([[audit_static_analysis_blindspots]]).

## 4. API — `api/routes/medical.py`, схемы `schemas/medical.py`

| Эндпоинт | Метод | Назначение |
|---|---|---|
| `/medical/factors` | GET | список 29н-факторов тенанта (фильтр `category`) |
| `/medical/factors` | POST | создать фактор (409 на дубль `code`) |
| `/medical/factors/{id}` | GET / PATCH / DELETE | жизненный цикл фактора |
| `/medical/contingent/register` | GET | документ «контингент» (29н) |
| `/medical/named-list` | GET | документ «поименный список» (29н) |

- ABAC: чтение — read-роли медосмотров; запись факторов — write-роли (как у `/medical/norms`). Feature-gate `medical` (как есть).
- Привязка `medical_factor_code` к hazard: в этом срезе выставляется через **demo-seed и прямую установку поля** (`RiskHazard.medical_factor_code`); движок и документы читают его. Runtime-CRUD маппинга hazard→factor (через апдейт risk-hazard или отдельный эндпоинт) **отложен в Срез-3** — он не нужен для рабочего factor-driven контингента и его проверки. Это держит срез сфокусированным на движке+документах.

## 5. Автоматизация и demo-seed

- **Beat:** существующий `medical.contingent.tick` (03:00 UTC) уже зовёт `notify_overdue` поверх `compute_contingent` — после расширения движка он автоматически охватывает factor-driven контингент. Новый beat **не нужен**.
- **Demo-seed** (`demo_bootstrap`): 2-3 фактора 29н (напр. шум «4.4»/12мес/periodic; химические «1.1»/12мес/periodic; работы на высоте «6.1»/`work`/12мес/periodic), маппинг demo-hazards (`RiskHazard.medical_factor_code`), и хотя бы один demo-`Person` в должности с замапленным hazard **без** ручной нормы — чтобы он появился в поименном списке и контингенте именно factor-driven путём.

## 6. Тестирование

По слоям (локально Py3.13.7/.venv, PowerShell→file; канон Py3.12 = CI, выключен):

- **Модель+миграция:** guard `medical_factor` (цепочка `ed03→med02`, состав таблицы/колонки, FK-отсутствие, downgrade-симметрия).
- **Чистый движок:** `factors_for_hazards` (маппинг/пропуск немапленных), `required_exams_from_factors` (объединение видов, строжайшая периодичность при конфликте).
- **Документы:** контингент (группировка по должности, headcount активных, факторы), поименный список (ФИО/должность/подразделение/факторы/даты/статус); factor-driven путь даёт строки **без** ручной нормы.
- **API:** CRUD факторов (409 дубль `code`), `/contingent/register`, `/named-list`; ABAC read/write, tenant-изоляция, feature-gate.
- **Parity/регрессия Среза-1:** существующие контингент/норм-тесты зелёные (back-compat); `compute_contingent` норм-путь не изменён.

## 7. Декомпозиция на потоки (для исполнения)

Естественные слои с зависимостями данные → движок → документы. Независимо-параллелизуемые листья:
- **Поток A (фундамент):** модель `MedicalFactor` + миграция `med02` + `RiskHazard.medical_factor_code` + CRUD-API факторов + guard-тест. Блокирует B/C по форме модели.
- **Поток B (движок):** чистые функции `factors_for_hazards`/`required_exams_from_factors` + расширение `compute_contingent` + unit-тесты движка. Разрабатывается против согласованного интерфейса `FactorTuple`.
- **Поток C (документы):** `build_contingent_register` + `build_named_list` + API + тесты документов. Зависит от B.

Исполнение — subagent-driven (implementer + review на задачу); параллельность там, где листья реально независимы (CRUD-факторов A ∥ unit-движка B против согласованного `FactorTuple`; документы C — после B). Demo-seed и parity-регрессия — финальный поток.

## 8. Связь с памятью

[[tz-section-b-ground-truth]] (медосмотры Срез-1 ВЛИТ; §9.2 авто-контингент-из-штатки был отложен) · [[audit-static-analysis-blindspots]] (литералы имён таблиц в миграциях) · [[ci-disabled-actions-off]] (local-evidence, канон Py3.12 CI выключен) · [[workflow-prodolzhay-po-tz]].
