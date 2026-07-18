# P10-03 Медосмотры — срез «Психиатрическое освидетельствование (342н)» — Design

**Дата:** 2026-07-09
**Контур:** P10-03 Медосмотры (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md:655`; ТЗ `B.8` → `vNext §9.1/§9.2`, `TZ_FULL_UNIFIED.md:349`)
**Предшественники (в main):** контингент (norm-driven ∪ 29н-factor-driven), направления (`MedicalReferral` FSM + CRUD + transition + `generate_due_referrals`), отстранение (`MedicalSuspension` авто-open/lift + `person_admission` блок допуска), печатные формы 29н. Всё это **готовый backend без психиатрической специфики**.
**Driver:** brainstorming → writing-plans → subagent-driven-development.
**Head-миграция на старте:** цепочка линейна `wa08 → wa09 → wh01`; единственный head — `20260709_wh01_webhook_delivery_outbox_id`. Новая миграция `20260709_med03_psychiatric_342n` (revision `20260709_med03_psychiatric_342n`, `down_revision = "20260709_wh01_webhook_delivery_outbox_id"`), следует medical-неймингу `medNN`.
**База ветки:** `main` (текущая рабочая ветка `claude/tz-continuation-10b723` == main). Новая ветка от main. Независимый срез — миграция чисто аддитивная.

## Цель

Закрыть **единственную настоящую функциональную дыру** контура медосмотров: сегодня
`MedicalExamKind.PSYCHIATRIC` существует лишь как значение enum + периодичность 1825 дней +
метка на печати — **нет механизма «кто подлежит»** обязательному психиатрическому освидетельствованию
(ОПО) и **нет записи решения врачебной комиссии**. Три остальных названных в ТЗ пробела
(контингент / направления / отстранение) уже имеют рабочий backend — им не хватает UI/данных, а не логики.

Психиатрическое освидетельствование (приказ Минздрава РФ № 342н «Порядок прохождения обязательного
психиатрического освидетельствования…»; перечень видов деятельности — ПП РФ № 695 от 28.01.2021)
структурно **отличается** от обычного медосмотра:
- решает **врачебная комиссия** медорганизации, а не один врач;
- вердикт — «медицинские психиатрические **противопоказания** к **конкретным видам деятельности**
  выявлены / не выявлены», привязка к **видам деятельности** (управление транспортом, работы на высоте,
  обслуживание электроустановок, оборот оружия, сосуды под давлением, аварийно-спасательные работы,
  подземные работы, …), **не** к 29н-фактору вредности;
- периодичность — не реже 1 раза в 5 лет (текущий дефолт 1825 дней уже верен).

**Ключевое наблюдение (почему срез мал):** цепочка направление → авто-отстранение → блок допуска уже
срабатывает на `fitness=UNFIT` (`domains/medical/service.py` `_apply_suspension` → `person_admission.py:130`);
`MedicalReferral` уже несёт `exam_kind=PSYCHIATRIC`; `generate_due_referrals` уже выпускает направления на
всё, что контингент помечает overdue/missing. Достаточно **научить `compute_contingent` понимать, что
должность подлежит ОПО** — и направление, отстранение, блок допуска зажигаются «бесплатно». Единственное
по-настоящему новое — **ось «кто подлежит»**, потому что психиатрия ключуется на **виды деятельности (695)**,
а не на 29н-факторы. Это **вторая ось деривации контингента**, параллельная существующей 29н-оси.

## Принятые решения (brainstorming, 2026-07-09, AskUserQuestion)

1. **Контур = P10-03 Медосмотры** (следующий partial `[v1.1]` после закрытого P10-06 СИЗ-склад и влитого
   код-ревью-свипа PR #728).
2. **Под-срез = Психиатрия 342н (backend-forward)** — единственная настоящая функциональная дыра из четырёх
   названных в ТЗ (контингент/психиатрия/направления/отстранение); три остальных = «backend готов, нужен UI».
3. **Моделирование = каталог видов деятельности (695) + расширенный `MedicalExam`** (не выделенная модель
   `PsychiatricAssessment`, не «минимальный флаг на позиции»). Освидетельствование = `MedicalExam(kind=PSYCHIATRIC)`
   + несколько psychiatry-полей; переиспользует referral + suspension. Минимум дублирования, точно ложится
   в существующую машинерию (parallel to 29н `MedicalFactor`).
4. **Периодичность = 5 лет по умолчанию, переопределяемо per вид деятельности** в каталоге (зеркало
   `MedicalNorm.interval_days` / `MedicalFactor.periodicity_months`).
5. **Объём среза = backend + тонкая UI-секция** на `MedicalPage` (как все срезы P10-06), чтобы не плодить
   «невидимый backend».
6. **Сидинг каталога 695 (делегировано агенту):** demo-сидинг в `demo_bootstrap` (работает из коробки в dev)
   **+ on-demand эндпоинт** `POST /medical/psychiatric/activity-types/seed-defaults` (one-click загрузка
   стандартного списка для любого тенанта). Стандартный список 695 живёт **одной кодовой константой** —
   единый источник и для bootstrap-сида, и для эндпоинта. Каталог остаётся tenant-scoped и редактируемым
   через CRUD (консистентно с `MedicalFactor`; отвергнут per-tenant data-migration как анти-паттерн этой кодбазы).

## Инвариант (обязательный якорь)

Существующая машинерия медосмотров не ломается: contingent/referral/suspension-тесты остаются зелёными.
Психиатрия **добавляется как union-слагаемое** в `compute_contingent`, не переписывая 29н-ветку. Расширение
`MedicalExam` — только nullable/defaulted колонки (обратная совместимость записей без психиатрии).

## Архитектура

### 1. Модель — миграция `med03` (чисто аддитивная)

Две новые tenant-scoped таблицы (паттерн `MedicalFactor`):

- **`PsychiatricActivityType`** (`psychiatric_activity_type`, `TenantBaseModel`) — каталог видов деятельности 695:
  - `code` `String(32)`, `name` `String(255)`, `interval_days` `Integer` default `1825` (переопределяемая
    периодичность per-вид), `UniqueConstraint(tenant_id, code)`.
- **`PsychiatricPositionActivity`** (`psychiatric_position_activity`, `TenantBaseModel`) — маппинг
  «должность → вид деятельности» (параллель `RiskHazard.medical_factor_code`, но отдельной join-строкой,
  т.к. привязка позиционная, не hazard-уровня):
  - `position_id` `ForeignKey(position.id)` index, `activity_code` `String(32)`,
    `UniqueConstraint(tenant_id, position_id, activity_code)`.

Две новые колонки на `medical_exam` (расширенный exam, без новой таблицы освидетельствования):
- `psychiatric_protocol_no` `String(128)` nullable — № решения/протокола врачебной комиссии.
- `psychiatric_activity_codes` JSON list (`MutableList`, default `[]`) — виды деятельности, охваченные
  освидетельствованием.

Переиспользуется как есть: `exam_kind=PSYCHIATRIC`, `medical_org_name` (медорганизация/комиссия),
`fitness` (`FIT` = противопоказаний нет / `UNFIT` = выявлены), `contraindications` (list кодов видов
деятельности с противопоказаниями или текст), `valid_until`.

### 2. Чистая логика — `domains/medical/lifecycle.py` (ORM-free, параллель 29н)

- `ActivityTuple = tuple[str, str, int]` — `(code, name, interval_days)`, ORM-free вид деятельности.
- `psychiatric_required(activity_codes: set[str], catalog: Iterable[ActivityTuple]) -> bool` — должность
  подлежит ОПО ⇔ у неё есть ≥1 замапленный вид деятельности, присутствующий в каталоге.
- `psychiatric_interval(activity_codes, catalog) -> int` — строжайший (min) `interval_days` среди
  замапленных видов; fallback `DEFAULT_INTERVAL_DAYS[PSYCHIATRIC]` = 1825.

Юнит-тестируется без БД (как `factors_for_hazards`/`required_exams_from_factors`).

### 3. Интеграция контингента — `domains/medical/service.py`

В `compute_contingent`: батч-загрузка каталога видов деятельности + маппинга position→activity (без N+1,
как `_load_factor_catalog`), затем для каждого человека — если его должность подлежит ОПО, добавить
`PSYCHIATRIC` в `required`. Существующие `classify()` / `valid_until` дают `ok/due_soon/overdue/missing`
для психиатрии ровно как для любого kind. `valid_until` психиатрического экзамена считается через
`compute_valid_until(exam_date, psychiatric_interval(...))`. `status_summary` подхватывает автоматически.

Регистр/поименный список 29н (`build_contingent_register`/`build_named_list`) в этом срезе **не трогаем**
(они factor-driven, семантика 29н-формы). Психиатрический контингент виден через `GET /medical/contingent`.

### 4. Направление / отстранение / блок допуска — **ноль нового кода**

- **Направление:** `generate_due_referrals` уже выпускает направления на overdue/missing kinds контингента →
  психиатрические направления пойдут автоматически, как только (3) внесёт `PSYCHIATRIC` в контингент.
  *Верифицировать в интеграционном тесте, что путь действительно идёт через `compute_contingent`.*
- **Отстранение:** запись `MedicalExam(kind=PSYCHIATRIC, fitness=UNFIT)` через `record_exam` →
  `_apply_suspension` открывает `MedicalSuspension` → `person_admission.py:130` блокирует допуск.
  Удовлетворяет §9.2 «блокировать допуск при противопоказании».
- **Осознанно отложено:** per-activity частичное ограничение (блокировать только конкретный вид
  деятельности, не всю работу) — этот срез блокирует консервативно/полностью.

### 5. API — `routes/medical/` (за существующим флагом `medical`, та же RBAC)

Каталог видов деятельности (зеркало factors CRUD в `catalog.py`):
- `GET /medical/psychiatric/activity-types` (list, ETag), `POST /…` (create),
  `GET/PATCH/DELETE /medical/psychiatric/activity-types/{id}`.
- `POST /medical/psychiatric/activity-types/seed-defaults` — идемпотентно вставляет стандартный 695-набор
  для текущего тенанта (пропускает уже существующие `code`); audit.

Маппинг должность→вид деятельности (зеркало `hazard-factors` / `set_hazard_factor`):
- `GET /medical/psychiatric/position-activities` (list),
  `PUT /medical/positions/{position_id}/psychiatric-activities` (set полного набора кодов позиции; audit).
  Неизвестный `activity_code` → 422 (как `medical_factor_not_found`).

Запись освидетельствования — переиспользует существующие `POST /medical/exams` / `PATCH /medical/exams/{id}`;
схемы `MedicalExam*` расширяются двумя полями (`psychiatric_protocol_no`, `psychiatric_activity_codes`).

Общие контракты: `MedicalFeatureGate` (флаг off → 404), tenant-iso, write-роли admin/owner/hr, audit на write.

### 6. Сидинг 695 — `PSYCHIATRIC_ACTIVITY_DEFAULTS` (кодовая константа)

Одна константа (напр. `domains/medical/psychiatric_defaults.py`) со стандартным списком видов деятельности
по ПП РФ № 695: `(code, name, interval_days=1825)`. Используется:
- `demo_bootstrap._seed_psychiatric_activities_demo` — сидит для demo-тенанта (параллель
  `_seed_medical_factor_demo`) + мапит demo-должность(и) на 1-2 вида (чтобы психиатрический контингент был
  виден из коробки).
- эндпоинтом `seed-defaults` — для любого тенанта on-demand.

Точные формулировки видов деятельности — по тексту ПП РФ № 695 (не выдумывать; при неуверенности —
консервативная формулировка + пометка сверить с первоисточником).

### 7. Frontend — тонкая секция на `MedicalPage.tsx`

Read-first секция «Психиатрическое освидетельствование (342н)»:
- каталог видов деятельности (список + кнопка «Загрузить стандартный список 695» → `seed-defaults`);
- редактор маппинга должность→виды деятельности;
- психиатрический контингент (реюз `GET /medical/contingent`, фильтрация по `exam_kind=psychiatric`
  на клиенте).
`operationsApi` (или профильный medical-api клиент) получает новые методы. House-style, хардкод RU-строк,
без нового маршрута (секция на существующей `/medical`).

## Тестирование + гейты (проверенная каденция)

TDD по задаче:
- **Pure-logic юниты:** `psychiatric_required` / `psychiatric_interval` (пусто/один/несколько/min-interval/
  неизвестный код).
- **Миграция:** round-trip upgrade/downgrade (PG16-гейт `local_gate.py --db-only`).
- **Интеграция контингента:** должность подлежит → `PSYCHIATRIC` появляется в `compute_contingent` →
  `generate_due_referrals` выпускает психиатрическое направление → запись `UNFIT`-экзамена открывает
  `MedicalSuspension` → `person_admission` блокирует допуск (сквозной якорь §9.2).
- **API:** каталог CRUD, `seed-defaults` идемпотентность, маппинг set/list, tenant-iso, flag-off → 404,
  422 на неизвестный код / `interval_days<=0`.
- **Existing-green якорь:** contingent/referral/suspension-тесты зелёные (расширение не сломало 29н-ветку).
- **Фронт:** vitest секции MedicalPage, `tsc`, `vite build`.

Гейты перед PR: backend-регресс батчами (PowerShell, timeout 600000, один прогон — холодный импорт 2-3 мин),
**ruff + black** (re-run тестов после black — авто-формат ломает substring-ассерты миграций), **OpenAPI baseline
re-snap** (чисто аддитив: новые роуты + схемы, 0 удалений — ARCH-4), **PG16 `local_gate.py --db-only`** для
миграции (ARCH-3 boundaries clean).

## Вне объёма (follow-up, НЕ этот срез)

- Per-activity частичное ограничение (блок только противопоказанного вида деятельности, не всей работы) —
  нужна связка suspension↔activity.
- Выделенная печатная форма направления на ОПО / решения врачебной комиссии (сейчас печатаются только
  агрегатные 29н-формы).
- Психиатрический регистр / поименный список (отдельные print-формы под 342н).
- Полное моделирование состава врачебной комиссии (члены/председатель) — сейчас `medical_org_name` + № протокола.
- «По показаниям» повторное освидетельствование сверх 5-летней каденции.
- Frontend для направлений/отстранений/контингента (три остальных названных пробела) — отдельный фронт-срез.

## Файлы (ориентир)

- `backend/app/models/medical.py` — +`PsychiatricActivityType`, +`PsychiatricPositionActivity`, +2 колонки `MedicalExam`.
- `backend/app/migrations/versions/20260709_med03_psychiatric_342n.py` — новая аддитивная миграция (от `wh01`-head).
- `backend/app/domains/medical/lifecycle.py` — +`ActivityTuple`, +`psychiatric_required`, +`psychiatric_interval`.
- `backend/app/domains/medical/service.py` — `compute_contingent` (+psychiatric union), +загрузчики каталога/маппинга.
- `backend/app/domains/medical/psychiatric_defaults.py` — `PSYCHIATRIC_ACTIVITY_DEFAULTS`.
- `backend/app/api/routes/medical/psychiatric.py` (новый роут-модуль) — каталог CRUD + seed-defaults + маппинг.
- `backend/app/schemas/medical.py` — psychiatric-схемы + расширение `MedicalExam*`.
- `backend/app/services/dev_bootstrap.py` / `demo_bootstrap.py` — demo-сид видов деятельности + маппинг.
- `frontend/src/pages/medical/MedicalPage.tsx` + api client — тонкая секция.
- Тесты: `backend/tests/test_medical_psychiatric_*.py` (юниты/интеграция/API), фронт-vitest.
