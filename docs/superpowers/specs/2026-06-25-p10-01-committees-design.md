# P10-01 «Комитеты / комиссии / заседания» — Срез-1 (design)

- **Дата:** 2026-06-25
- **Статус:** проект (design), ожидает ревью пользователя
- **Под-проект roadmap:** `P10-01` (раздел B, тег `[v1.1]`) — следующий «next-up» по [`docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`](../../roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md) (Section B reconciliation 2026-06-25).
- **Канон ТЗ:** [`TZ_FULL_UNIFIED.md` B.17](../../spec/TZ_FULL_UNIFIED.md) / [`PLATFORM_VNEXT_UPGRADE_SPEC.md` §18](../../spec/PLATFORM_VNEXT_UPGRADE_SPEC.md).
- **Объём решения пользователя:** *Срез-1 skeleton, backend + тонкий UI; задачи решений — выделенной таблицей.*

---

## 1. Контекст и находка

`vNext §18` требует зрелый модуль (не «дополнение к документам»): комитеты ОТ/ПБ, комиссии (обучение/расследования), повестки, приглашения, протоколы, решения, голосование, задачи по решениям, контроль исполнения, журнал заседаний, KPI исполнения решений.

**Состояние по коду (greenfield, подтверждено `git grep`):** ни одной модели комитет/комиссия/заседание/повестка/голосование/решение нет. Совпадения `commission` — это подстрока `decommissioned` и общий **document-approval** workflow (`approval_workflow.py`, `approval_orchestration.py`), который про согласование документов, а не про governance заседаний. Пересечения нет — строим с нуля.

**Контур задач (task-модели в репо):** `CorrectiveAction`/CAPA, `PlanTask` (×2 — известный дубль-класс хазард), `ApprovalTask`, `obligations.Task` — ни одна не про решения комитетов. Решение пользователя: **выделенная таблица** в собственном bounded-context (избегаем сцепления и `PlanTask`-дубля).

---

## 2. Архитектура

Новый bounded-context `committees`, **аддитивно**, за feature-флагом, по проверенному шаблону Section-B (work_permits / contractors / medical):

- **Модели:** новый файл `backend/app/models/committees.py` (НЕ в раздутый `models.py` — источник дубль-класс хазардов).
- **Домен:** `backend/app/domains/committees/{__init__,service,lifecycle}.py`.
- **Роуты:** `backend/app/api/routes/committees.py` (tenant-scoped deps, `compute_list_etag` на list-эндпоинтах, RBAC через существующий module-access guard).
- **Миграция:** префикс `cmt01` (`cm01` занят — `20260623_cm01_company_status_tags_person_position.py` на main). Аддитивная, симметричный downgrade (round-trip guard — урок migration-downgrade-repair).
- **Флаг:** `committees` через `app.core.feature_flags.is_feature_enabled(session, tenant_id, "committees", default=False)` — **default OFF**, без глобального рефактора.
- **Frontend:** одна страница `frontend/src/pages/committees/CommitteesPage.tsx` + api/store-срез (по образцу `operationalDashboard`/ppe).

**Отвергнутые альтернативы:** (B) вшить в `approval_workflow` — другой bounded-context, сцепляет governance с подписанием документов; (C) модели в общий `models.py` — раздут (3000+ строк), источник дубль-классов.

---

## 3. Модель данных (срез-1, 6 таблиц)

Все таблицы tenant-scoped (`TenantBaseModel`).

| Таблица | Назначение | Ключевые поля |
|---|---|---|
| `committee` | Комитет/комиссия | `kind` enum (`osms` / `pb` / `commission_training` / `commission_investigation` / `other`), `name`, `description`, `is_active` |
| `committee_member` | Состав | FK→`committee`, `person_id`, `role` enum (`chair` / `secretary` / `member`) |
| `committee_meeting` | Заседание | FK→`committee`, `scheduled_at`, `location`, `status` enum (`planned` / `held` / `cancelled`) |
| `committee_agenda_item` | Пункт повестки | FK→`committee_meeting`, `seq`, `title`, `presenter_person_id` (nullable) |
| `committee_decision` | Решение | FK→`committee_meeting`, FK→`committee_agenda_item` (nullable), `text`, `decided_at` |
| `committee_decision_task` | Задача по решению | FK→`committee_decision`, `assignee_person_id`, `due_date`, `status` enum (`open` / `in_progress` / `done` / `overdue`), `evidence_note` (nullable) |

**Enum-дисциплина (уроки enum-pg-label-parity):** native-enum с явным `name=`, лейблы PG = `.value`; новые типы добавляются в инвентарь native-enum guard-теста.

**«Протокол»** в срез-1 — НЕ отдельная таблица, а read-проекция: агрегат решений + задач заседания (`GET …/protocol`). Отдельный реестр-журнал и нумерация протоколов — срез-2.

---

## 4. Lifecycle (`domains/committees/lifecycle.py`)

- Переходы заседания: `planned → held`, `planned → cancelled`, `held → cancelled`. Прочие → `409 Conflict`.
- Решения (`committee_decision`) создаются только на заседании со `status = held` (иначе 409).
- `overdue` у задачи — **вычисляется на чтении** (`due_date < today AND status ∉ {done}`), без фонового джоба в срез-1. Хранимый `status` остаётся `open`/`in_progress`/`done`; `overdue` — производный флаг в ответе.

---

## 5. API (`api/routes/committees.py`)

```
GET/POST   /api/v1/committees                          # list+create (ETag)
GET/PATCH  /api/v1/committees/{id}                     # detail+update
POST       /api/v1/committees/{id}/members             # add member
DELETE     /api/v1/committees/{id}/members/{mid}       # remove member
GET/POST   /api/v1/committees/{id}/meetings            # list+schedule (ETag)
GET/PATCH  /api/v1/committees/meetings/{mid}           # detail+transition status
POST       /api/v1/committees/meetings/{mid}/agenda-items
POST       /api/v1/committees/meetings/{mid}/decisions # 409 если meeting.status≠held
GET        /api/v1/committees/meetings/{mid}/protocol  # read-проекция (decisions+tasks)
POST       /api/v1/committees/decisions/{did}/tasks
PATCH      /api/v1/committees/tasks/{tid}              # update status/evidence
```

- ETag на list-эндпоинтах через `compute_list_etag` (304 при совпадении).
- Все запросы/мутации tenant-scoped; чужой tenant → 404/no-leak.
- Переходы статусов — через `lifecycle.py`; отказ → 409.

---

## 6. Frontend (тонкий)

Одна страница `CommitteesPage.tsx` + api/store-срез (паттерн `operationalDashboard`/ppe), за флагом `committees`:
- список комитетов → карточка (состав + заседания);
- карточка заседания: повестка, решения, задачи со статус-бейджами (вкл. `overdue`).
Переиспользуем существующие list/empty/error/retry паттерны. Новой дизайн-системной работы нет.

---

## 7. Тестирование

- **Unit:** переходы lifecycle (валидные/невалидные → 409), вычисление `overdue`, гард «решение только на held».
- **API-контракт:** CRUD по всем эндпоинтам, ETag 304, RBAC (module-access), cross-tenant 404/no-leak — плотность ≥ ppe/work_permits контрактов.
- **Enum guard:** новые native-enum колонки внесены в инвентарь.
- OpenAPI обновлён; CHANGELOG; seed-данные для демо (1 комитет + заседание + решение + задача).

---

## 8. Acceptance (срез-1)

- Цепочка `committee → meeting → agenda → decision → task` работает end-to-end (API + UI).
- ETag на list-эндпоинтах; tenant-isolation тесты зелёные; lifecycle-гарды enforced; флаг `committees` (default off) изолирует модуль.
- Все новые тесты зелёные (паттерн прогона — Py3.12.12 локально / CI source-of-truth).
- В [`TZ_COVERAGE_MATRIX.md`](../../audit/TZ_COVERAGE_MATRIX.md) / roadmap-реконсиляции: `P10-01` → `partial` (срез-1 done), отложенные пункты перечислены явно.

---

## 9. Явно отложено в срез-2 (не «потеряно»)

Записать в матрицу как остаток `P10-01`:
- **голосование** (кворум, учёт голосов, типы решений по большинству);
- **приглашения / уведомления** участникам (поверх готового notification-контура);
- **KPI исполнения решений** (дашборд: % закрытия в срок, просрочки по ответственным);
- **журнал заседаний** как отдельный реестр + нумерация протоколов;
- **проекция задач решений в Command Center** (overdue/неназначенные — в общий операционный дашборд W2).

---

## 10. Обязательные правила (§E канона / §36 vNext)

Не ломать рабочие модули; additive-миграция; не удалять API без слоя совместимости; новая функция за feature-флагом; tenant isolation на всех границах; bounded context через события (для срез-2 проекций); unit/integration тесты; OpenAPI + CHANGELOG + seed; строгая типизация (backend + frontend).

---

## 11. Следующий шаг

1. Ревью этого спека пользователем.
2. `writing-plans` → детальный план реализации срез-1.
3. Реализация (TDD) → обновить матрицу/handoff.
