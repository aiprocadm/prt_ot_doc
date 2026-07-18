# Доводка контура «Медосмотры» до объёма — дизайн (Срез 1 «Ядро учёта» + Контингент/Автоматизация)

- **Дата:** 2026-06-07
- **Статус:** design / proposal — ожидает финальной вычитки пользователем перед writing-plans
- **Контур ТЗ:** раздел B.8 «Медосмотры, психиатрия, здоровье» (`docs/spec/TZ_FULL_UNIFIED.md`), детальная рамка — `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md §9`.
- **Критерии приёмки:** раздел F.4 ТЗ («СОУТ влияет на медосмотры/СИЗ/риски; результаты редактируемы/версионируемы»).
- **Правила доработки:** раздел E ТЗ (additive миграции, feature flags, tenant isolation, bounded contexts через события, тесты, OpenAPI, seed, строгая типизация).
- **Выбранный подход:** **A** — аддитивное расширение существующего `medical_exam` + новый домен `domains/medical/` по образцу `prescriptions`. Без «двух параллельных схем».

---

## 1. Контекст и состояние (по code-аудиту 2026-06-07)

Медосмотры — **самый тонкий** partial-контур раздела B (~10%): есть только read-side.

**Что есть:**
- Модель `MedicalExam` ([backend/app/models/models.py:812](../../../backend/app/models/models.py)) — 5 полей: `person_id, exam_type (free String), exam_date, conclusion, valid_until`. **Нет** статуса годности, противопоказаний, направлений, медорганизаций, типов.
- Роут `GET /medical/exams` ([backend/app/api/routes/medical.py:51](../../../backend/app/api/routes/medical.py)) с ETag; `POST /medical/requirements` — заглушка, создаёт generic `Task` через `create_medical_task`. **Write-path осмотра отсутствует.**
- Read-side уже завязан на `medical_exam.valid_until`: блок допуска ([services/tasks.py:226](../../../backend/app/services/tasks.py) `_enforce_person_invariants`, дубликат в [packs.py:367](../../../backend/app/api/routes/packs.py)), календарь ([services/calendar_aggregator.py:343](../../../backend/app/services/calendar_aggregator.py)), дашборд ([modules/operational_dashboard/service.py:112](../../../backend/app/modules/operational_dashboard/service.py)), DQ ([modules/data_quality/rules.py:270](../../../backend/app/modules/data_quality/rules.py)).

**Опоры-паттерны для зеркалирования:**
- `PPENorm` ([models.py:1286](../../../backend/app/models/models.py)) — норма `position_id + hazard_id → требование + interval_days`.
- `prescriptions` — `domains/prescriptions/{lifecycle,service}.py` (чистый FSM + I/O-сервис), `routes/prescriptions.py` (`/transition`, `/overdue`, `/summary`, `/remind-overdue`), celery-beat `prescriptions.escalate.tick`, миграция `wa03`.
- Каталог событий ([services/events.py:183](../../../backend/app/services/events.py)) — `EventType` + типизированные payload + `_PAYLOADS` + `dedupe_key_for`.
- `native_enum()` ([models.py:1322](../../../backend/app/models/models.py)) — корректные lowercase PG-метки (см. enum-parity арку #633→#640).
- Feature-gate `require_warehouse_feature` ([ppe.py:377](../../../backend/app/api/routes/ppe.py)) — per-tenant DB-флаг.

## 2. Объём

**В этом спеке (Срез 1 + автоматизация, §9.1 ядро + §9.2):**
- Реальный write-path осмотра (результат + годность + противопоказания).
- Таксономия типов осмотров (enum).
- Направления (referral) как сущность + FSM.
- Противопоказания → отстранение → блок допуска (безопасностный цикл).
- Нормы медосмотров + вычисляемый контингент.
- Влияние СОУТ через нормы, привязанные к факторам/классу условий труда позиции.
- Автоматизация: контингент → направления (идемпотентно) + daily-эскалация.

**Отложено (явно, отдельные срезы):**
- Договоры с медорганизациями, бюджет безопасности (§9.1 хвост, §12.4) — Срез 3.
- Авто-генерация контингента из штатки полностью (§9.2) — здесь только норм-driven резолюция; импорт оргструктуры — позже.
- Полный импорт карт СОУТ (§10) — отдельный контур.
- §9.3 health-контур (предсменные/транспортные, медоборудование) — `[v1.2]`.

## 3. Архитектура (зеркало `prescriptions`)

- `backend/app/domains/medical/lifecycle.py` — **чистый FSM, без DB/app-импортов**: переходы направления, периодичность/сроки, классификация контингента, резолюция требований (СОУТ), правило годность→отстранение.
- `backend/app/domains/medical/service.py` — **I/O-сервис**: запись осмотра, выдача/переход направления, вычисление контингента, авто-генерация направлений, открытие/снятие отстранения, summary.
- `backend/app/api/routes/medical.py` — расширение существующего роутера.
- `backend/app/schemas/medical.py` — расширение схем.
- `backend/app/services/person_admission.py` — **новый общий хелпер** блока допуска (de-dup `tasks.py` + `packs.py`).

## 4. Модель данных (всё additive)

### 4.1 Расширение `medical_exam` (новые колонки nullable/defaulted)
- `exam_kind` `MedicalExamKind` {periodic, preliminary, psychiatric, fluorography, health_book}.
- `fitness` `MedicalFitness` {fit, fit_with_restrictions, unfit} — **драйвер отстранения**.
- `restrictions` `Text|None`; `contraindications` `JSON` (список).
- `referral_id` FK→`medical_referral` (nullable); `medical_org_name` `String|None`.
- `valid_until` остаётся (read-side зависит); если не задан при записи — вычисляется из периодичности нормы для (position, kind), иначе из дефолтного интервала по типу.
- `exam_type` (старый free String) сохраняется как лейбл для back-compat.

### 4.2 `medical_norm` (зеркало `PPENorm`) — драйвер контингента + СОУТ
- `position_id` FK; `hazard_id` FK→`risk_hazards` (nullable); `exam_kind`; `interval_days`; `working_conditions_class` `String|None`.
- `TenantBaseModel` (без soft-delete, как PPENorm).
- unique(`tenant_id`,`position_id`,`hazard_id`,`exam_kind`).

### 4.3 `medical_referral` (направление, FSM)
- `person_id` FK; `exam_kind`; `due_at` `Date`; `status` `MedicalReferralStatus`; `medical_org_name|None`; `issued_by|None`; `result_exam_id` FK→`medical_exam` (nullable, ставится при COMPLETED).
- `TenantBaseModel` + `SoftDeleteMixin`.

### 4.4 `medical_suspension` (отстранение)
- `person_id` FK; `reason` {unfit, contraindication}; `source_exam_id` FK→`medical_exam` (nullable); `started_at`; `lifted_at|None`; `status` {active, lifted}; `lifted_by|None`.
- `TenantBaseModel` + `SoftDeleteMixin`. **Активное отстранение блокирует допуск.**
- Отдельная запись, а **не** перегрузка `Person.employment_status` (HR-поле) — провенанс остаётся медицинским.

### 4.5 Enums и миграция
- Все enums через `native_enum()` (lowercase PG-метки).
- Одна additive Alembic-ревизия: `add_column` на `medical_exam` (nullable/defaulted), `create_table` ×3, `CREATE TYPE` для enums.
- Симметричный downgrade (drop таблиц → drop колонок → drop enum-типов) — round-trip upgrade→downgrade→upgrade зелёный (по урокам downgrade-repair, PR #639).

## 5. Доменная логика (`domains/medical/lifecycle.py` — чистые функции)

### 5.1 FSM направления
```
ISSUED    → {SCHEDULED, CANCELLED}
SCHEDULED → {COMPLETED, CANCELLED}
COMPLETED → {}   (terminal)
CANCELLED → {}   (terminal)
TERMINAL = {COMPLETED, CANCELLED}
```
- `validate_transition(current, target)` + `InvalidTransition`; self-transition = идемпотентный no-op.
- `is_overdue(due_at, status, today) = due_at < today and status not in TERMINAL` (просрочка — вычисляемая, не статус).
- `requires_result(target) = (target == COMPLETED)` — закрытие требует `result_exam_id`.

### 5.2 Периодичность
- `compute_valid_until(exam_date, interval_days) -> date = exam_date + interval_days`.
- `next_due(last_exam_date | None, interval_days, today) -> date` = `today` если осмотра не было, иначе `last_exam_date + interval_days`.

### 5.3 Классификация контингента (`ContingentItemStatus`)
`classify(latest_valid_until | None, today, warning_days) ->`
- `MISSING` — осмотра нет, норма требует;
- `OVERDUE` — `valid_until < today`;
- `DUE_SOON` — `valid_until <= today + warning_days`;
- `OK` — иначе.

### 5.4 Резолюция требований = влияние СОУТ
`resolve_required_kinds(position_id, working_conditions_class, hazard_ids, norms) -> set[MedicalExamKind]` — объединение норм, совпавших по позиции / классу условий труда / факторам опасности ([Position.hazards m2m, models.py:696](../../../backend/app/models/models.py)). Изменение факторов/класса позиции автоматически меняет набор требуемых осмотров.

### 5.5 Правило годность → отстранение
- `requires_suspension(fitness) = (fitness == UNFIT)`.
- `suspension_action(has_active_suspension, new_fitness) -> {OPEN, LIFT, NONE}`:
  - нет отстранения + UNFIT → **OPEN**;
  - есть активное + (fit | fit_with_restrictions) → **LIFT**;
  - иначе **NONE**.
  - Причина OPEN выводится сервисом из осмотра: `contraindication`, если `contraindications` непусты, иначе `unfit`. Просрочка/отсутствие осмотра блокирует допуск **без** записи отстранения (см. 6.1).
- `LIFT_SUSPENSION_ROLES = {admin, owner}` (segregation of duties, зеркало `VERIFY_ROLES`).

## 6. Интеграция с существующими потоками

### 6.1 Блок допуска
- **De-dup:** проверка инвариантов выносится в `services/person_admission.py::enforce_person_admission(...)`; `tasks.py` и `packs.py` зовут общий хелпер.
- **Новая блокировка:** активное `medical_suspension` → нарушение `"medical_suspension"` в контракте `{"code": "requirements_not_met", "details": [...]}`.
- **Norm-aware, back-compat:** если для позиции есть `medical_norm` — блок при любом требуемом `exam_kind` в статусе MISSING/OVERDUE. **Если норм нет — прежнее поведение** («есть валидный осмотр»), существующие тесты/потоки не ломаются.

### 6.2 Календарь / Дашборд / DQ (аддитивно)
- Календарь: + события сроков направлений (`referral.due_at`) и пробелов контингента (MISSING/OVERDUE).
- Дашборд: + счётчики активных отстранений и overdue/missing контингента.
- DQ: + правило «требуемый по норме осмотр отсутствует» и «вердикт unfit без активного отстранения».

### 6.3 События (реестр `events.py`)
- Новые `EventType`: `MEDICAL_EXAM_RECORDED="MedicalExamRecorded"`, `PERSON_SUSPENDED="PersonSuspended"`, `PERSON_REINSTATED="PersonReinstated"` — payload-классы + `_PAYLOADS` + ветки `dedupe_key_for`.
- Напоминания — переиспользование `TASK_DUE_SOON`/`TASK_OVERDUE` (idempotency-key с датой → дедуп на повторном прогоне).

### 6.4 Автоматизация контингент → направления
- `service.generate_due_referrals(...)` — для MISSING/OVERDUE требуемых kind'ов без открытого направления заводит `referral(status=ISSUED)`. Идемпотентно (пропуск, если открытое направление person+kind уже есть).
- On-demand: `POST /medical/contingent/generate-referrals`.
- Daily beat `medical.contingent.tick` (как `prescriptions.escalate.tick`): рассылка `TASK_DUE_SOON`/`TASK_OVERDUE` по пробелам и просроченным направлениям.

## 7. API (расширение `routes/medical.py`)

Паттерны: `abac(...)`-зависимости, ETag (`compute_list_etag`) на списках, `@audit_operation`.

**Осмотры:**
- `POST /medical/exams` — **новый write-path**: запись результата; UNFIT → авто-OPEN отстранения, fit → авто-LIFT; эмит `MedicalExamRecorded`.
- `GET /medical/exams` (есть; +фильтры kind/fitness), `GET /medical/exams/{id}`, `PATCH /medical/exams/{id}` (правка → пересчёт отстранения).

**Направления:** `GET/POST /medical/referrals`, `GET /medical/referrals/{id}`, `POST /medical/referrals/{id}/transition` (COMPLETED требует `result_exam_id`).

**Нормы:** `GET/POST /medical/norms`, `GET/PATCH/DELETE /medical/norms/{id}`.

**Контингент / автоматизация / сводка:**
- `GET /medical/contingent` — вычисляемый список (person × требуемый kind → ok/due_soon/overdue/missing), фильтры position/site/status.
- `POST /medical/contingent/generate-referrals` — идемпотентная автогенерация.
- `GET /medical/summary` — счётчики по статусам + overdue/missing + активные отстранения.

**Отстранения:** `GET /medical/suspensions`, `POST /medical/suspensions/{id}/lift` (admin/owner) → `PERSON_REINSTATED`.

**Back-compat:** `POST /medical/requirements` сохраняется, помечается legacy (заменён направлениями); API не удаляется (раздел E).

## 8. RBAC / feature-flag / tenant isolation

- **Роли:** write = admin/owner/hr (`_MEDICAL_WRITE_ROLES`); read += line_manager; **снятие отстранения = admin/owner**. Module-access «medical» уже в RBAC.
- **Feature-flag** `medical` (DB-driven, per-tenant, **default-ON**): гейтит новую поверхность (нормы/контингент/направления/отстранения); существующий `GET /medical/exams` не трогаем.
- **Tenant isolation:** все таблицы `TenantBaseModel`; все запросы tenant-scoped; cross-tenant 404/no-leak обязателен.

## 9. План тестов (раздел E)

- **Unit FSM** (без DB): переходы, `is_overdue`, `compute_valid_until`/`next_due`, `classify`, `resolve_required_kinds`, `suspension_action`.
- **API-контракт:** write-path осмотра, FSM направления, CRUD норм, вычисление контингента, идемпотентность generate-referrals, lift с 403 для не-admin.
- **Безопасностный цикл:** UNFIT → авто-отстранение → допуск заблокирован; fit → снятие → допуск проходит.
- **Допуск-block:** активное отстранение блокирует; norm-aware missing/overdue блокирует; без норм — старое поведение; общий хелпер зовётся из packs+tasks.
- **Миграция:** колонки/таблицы есть, additive, round-trip upgrade→downgrade→upgrade зелёный.
- **ETag-контракт** новых списков; **access-parity** (расширить); **cross-tenant**; **события** в outbox.
- **Seed/demo:** нормы + человек с пробелом контингента для демо календаря/контингента.
- **OpenAPI:** новые endpoints документируются (FastAPI авто).

## 10. Критерии приёмки (маппинг на ТЗ F.4 / §9)

1. Можно записать результат осмотра с типом, годностью и противопоказаниями (write-path).
2. Вердикт UNFIT автоматически открывает отстранение и блокирует допуск; fit — снимает.
3. `GET /medical/contingent` возвращает корректную классификацию (ok/due_soon/overdue/missing) на основе норм.
4. Изменение факторов/класса условий труда позиции меняет требуемые осмотры (влияние СОУТ).
5. Направления проходят FSM; контингент → направления генерируются идемпотентно; daily-эскалация шлёт напоминания.
6. Все новые list-endpoints отдают ETag; tenant-isolation подтверждён negative-тестами.
7. Миграция additive, round-trip зелёный; существующие допуск-потоки не сломаны (back-compat fallback).

## 11. Соответствие правилам (раздел E)

- Не ломаем рабочие модули (norm-aware блок с fallback); API не удаляем (legacy `/requirements`).
- Новая функциональность за feature-flag (`medical`, per-tenant).
- Additive миграции; tenant isolation на всех границах; bounded contexts через события.
- Тяжёлые/периодические операции — celery beat (`medical.contingent.tick`).
- Unit/integration тесты + seed + OpenAPI + строгая типизация (enums, Pydantic, mapped_column).

## 12. Открытые вопросы

Нет блокирующих. Параметры по умолчанию (warning_days=30 для DUE_SOON; default-ON флаг; periodicity из нормы) уточняются на этапе writing-plans как конфигурируемые константы.
