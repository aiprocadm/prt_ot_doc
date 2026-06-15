# Наряд-допуск §16: ядро + гейт допуска + mobile open/close + фото — дизайн

**Дата:** 2026-06-16
**Контур:** Наряды-допуски и работы повышенной опасности (ТЗ раздел B.15, vNext §16). **Срез-2 контура (после Срез-1 «личные допуски»).**
**Ветка:** `feat/work-permits` (стопкой поверх `feat/permits-lifecycle` — гейт переиспользует домен `permits` Среза-1; миграция `wp01` цепляется за `prm01`).
**Статус до среза:** Кода наряда-допуска НЕТ (grep по `work_permit`/`наряд` пуст). Существующая модель `Permit` — это **личный допуск** сотрудника (Срез-1, `domains/permits`), не путать. Есть образцы для всех частей: FSM (`domains/permits/lifecycle.py`, `domains/ppe/lifecycle.py`), связь один-ко-многим персон (`IncidentPerson`, `models.py`), гейт-блокировка (`services/contractor_admission.py`), файлы (`models/file.py` → `File`).

## 1. Цель среза

Построить **формальный документ «наряд-допуск на работы повышенной опасности»**: сам документ (вид работ, зона, оборудование, сроки, бригада, ответственные), жизненный цикл с приостановкой/продлением, блокировку выдачи при просроченных личных допусках/обучении/медосмотрах членов бригады, а также мобильное подтверждение открытия/закрытия с фотофиксацией.

### Не-цели среза (Срез-3+)
- Шаблоны нарядов-допусков; чек-листы.
- Каталоги-справочники видов работ / зон / оборудования (в этом срезе — простые поля).
- Загрузка файлов (используем существующий `File` по `file_id`; саму загрузку не строим).
- Фронтенд; авто-просрочка самого наряда (beat); печатные формы.

## 2. Решения по моделированию (зафиксировано на brainstorming)

- **Виды работ / зоны / оборудование — простые поля** (не каталоги): `work_type` — VARCHAR из фиксированного набора; `zone_text` (+ опц. FK `site_id`); `equipment_text` (свободный текст).
- **Люди — одна таблица `WorkPermitMember`** с `role` (и бригада, и ответственные единообразно; зеркало `IncidentPerson`).
- **Mobile open/close = переходы FSM + фото-событие** (а не отдельные под-статусы): «открыть» = `draft→issued`, «закрыть» = `→closed`; фото и история живут в `WorkPermitEvent`.
- **Статус — VARCHAR(32)** (анти-грабли enum-parity, как `permits`/`ppe`).

## 3. Архитектура

```
backend/app/
  domains/work_permits/
    __init__.py            # реэкспорт публичного
    lifecycle.py           # чистый FSM + константы статусов/ролей/видов работ
    service.py             # session-aware операции с документом + членами + событиями
  models/work_permit.py    # WorkPermit, WorkPermitMember, WorkPermitEvent
  services/work_permit_admission.py  # гейт готовности бригады (читает Permit/medical/training)
  schemas/work_permit.py
  api/routes/work_permits.py
  migrations/versions/20260616_wp01_work_permit_tables.py
```

### 3.1 Модели (`models/work_permit.py`, все `TenantBaseModel`)

**`WorkPermit`**
- `number: str | None` (номер наряда; если задан — unique по `(tenant_id, number)`).
- `work_type: str` (VARCHAR(32); одно из `WORK_TYPES`).
- `zone_text: str`; `site_id: str | None` (FK `site.id` ON DELETE SET NULL).
- `equipment_text: str | None`; `hazards_text: str | None`; `measures_text: str | None`.
- `planned_start: datetime | None`; `planned_end: datetime | None`.
- `status: str` (VARCHAR(32), default `"draft"`).
- `opened_at: datetime | None`; `closed_at: datetime | None`; `suspended_at: datetime | None`.
- Индексы: `(tenant_id, status)`, `(tenant_id, site_id)`.

**`WorkPermitMember`**
- `work_permit_id: str` (FK `work_permit.id` ON DELETE CASCADE, index).
- `person_id: str` (FK `person.id` ON DELETE RESTRICT, index).
- `role: str` (VARCHAR(32); одно из `MEMBER_ROLES`).
- UniqueConstraint `(tenant_id, work_permit_id, person_id, role)`.

**`WorkPermitEvent`** (история + фотофиксация open/close)
- `work_permit_id: str` (FK CASCADE, index).
- `event_type: str` (VARCHAR(32); одно из `EVENT_TYPES`).
- `at: datetime` (default now, tz-aware).
- `actor_user_id: str | None` (кто инициировал; из `access.user.id`).
- `photo_file_id: str | None` (FK `file.id` ON DELETE SET NULL — фото open/close).
- `note: str | None`.

> **Анти-грабли cross-base FK:** `Permit`/`Person`/`Site`/`File` — на `TenantBase`/`TenantBaseModel`. Новые FK ссылаются на эти таблицы в том же контуре tenant-схемы (как `IncidentPerson`→`person`). НЕ создавать FK на shared-base сущности. Имена таблиц/FK в миграции — литералами ([[audit_static_analysis_blindspots]]).

### 3.2 Чистый `lifecycle.py` (без I/O, зеркало `permits/lifecycle.py`)

Константы (VARCHAR-значения):
- `WORK_TYPES = {"hot_work","gas_hazardous","height","confined_space","excavation","electrical"}` (огневые/газоопасные/на высоте/замкнутое пространство/земляные/электро).
- `MEMBER_ROLES = {"issuer","supervisor","admitter","foreman","observer","member"}` (выдающий наряд / ответственный руководитель работ / допускающий / производитель работ / наблюдающий / член бригады).
- Статусы: `STATUS_DRAFT="draft"`, `STATUS_ISSUED="issued"`, `STATUS_SUSPENDED="suspended"`, `STATUS_CLOSED="closed"`, `STATUS_CANCELLED="cancelled"`; `WORK_PERMIT_STATUSES`.
- `EVENT_TYPES = {"issued","suspended","resumed","closed","cancelled","extended"}`.

FSM:
```
ALLOWED_TRANSITIONS = {
  draft:     {issued, cancelled},
  issued:    {suspended, closed, cancelled},
  suspended: {issued, closed, cancelled},
  closed:    {},
  cancelled: {},
}
```
- `WorkPermitTransitionError(ValueError)` (→ 409); `validate_transition(current, target)` отвергает и неизвестные статусы (как в hardened `permits`).
- Хелперы: `is_work_type(v)`, `is_member_role(v)` (валидация значений на уровне домена/схем).

### 3.3 Гейт допуска (`services/work_permit_admission.py`)

`check_brigade_readiness(session, *, tenant_id, work_permit_id) -> list[MemberViolation]` — на переходе `draft→issued`:

Для каждого `WorkPermitMember`:
1. **Личный допуск:** есть ли у `person_id` хотя бы один `Permit` со статусом `active` и не просроченный (`domains.permits.lifecycle.is_expired`)? Просроченный/отсутствующий активный → **BLOCK** (`violation="permit_expired"` / `"permit_missing"`).
2. **Медосмотр:** последний `MedicalExam` персоны с `valid_until < today` → **BLOCK** (`"medical_expired"`); полное отсутствие записи → **WARN** (`"medical_absent"`).
3. **Обучение:** есть ли `TrainingCertificate` с `valid_until < today` → **BLOCK** (`"training_expired"`); отсутствие → **WARN** (`"training_absent"`).

`MemberViolation` = `{person_id, role, code, severity}` (severity `block`/`warn`). Точные имена полей моделей `MedicalExam`/`TrainingCertificate` уточнить в плане чтением моделей (не выдумывать).

`enforce_brigade_readiness(...)` поднимает `WorkPermitBlocked` (→ 409 со списком violations), если есть хотя бы один `block`. `GET /{id}/readiness` возвращает полный список (block+warn) без выдачи.

### 3.4 Сервис (`domains/work_permits/service.py`, session-aware)

- `create_permit(...)` — создаёт draft.
- `update_permit(...)` — правка только в `draft` (иначе 409); `*_set`-флаги для очистки nullable (как в `permits`).
- `add_member(...)` / `remove_member(...)` — управление составом; добавление допустимо в `draft`/`issued`/`suspended` (не в терминальных).
- `issue(...)` — `enforce_brigade_readiness` → переход `draft→issued`, `opened_at=now`, событие `issued` (+опц. `photo_file_id`).
- `suspend(...)` / `resume(...)` — `issued↔suspended`, `suspended_at`, события `suspended`/`resumed`.
- `close(...)` — `issued/suspended→closed`, `closed_at=now`, событие `closed` (+опц. фото).
- `cancel(...)` — `→cancelled`, событие `cancelled`.
- `extend(...)` — обновляет `planned_end` (только в `issued`/`suspended`), событие `extended` (история продления).
- Все tenant-scoped; переходы через `lifecycle.validate_transition`; запись `WorkPermitEvent` в той же транзакции.
- `photo_file_id`/`site_id` валидируются на существование+тенант перед использованием.

### 3.5 Схемы (`schemas/work_permit.py`)
`WorkPermitCreate`/`Update`/`Read`/`Page`; `WorkPermitMemberCreate`/`Read`; `WorkPermitEventRead`; payload'ы действий: `IssueRequest{photo_file_id?, note?}`, `CloseRequest{photo_file_id?, note?}`, `SuspendRequest{note?}`, `ExtendRequest{planned_end}`; `ReadinessReport{ok: bool, violations: [...]}`. Валидация `work_type`/`role` через `lifecycle.is_*`.

### 3.6 API (`api/routes/work_permits.py`, префикс `/work-permits`, ABAC admin как `ppe`)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/work-permits` | список (фильтры `status`/`site_id`/`work_type`, пагинация) |
| POST | `/work-permits` | создать draft (201) |
| GET | `/work-permits/{id}` | деталь (+ члены + последние события) |
| PATCH | `/work-permits/{id}` | правка draft (409 если не draft) |
| DELETE | `/work-permits/{id}` | удалить draft (409 если не draft) |
| POST | `/work-permits/{id}/members` | добавить члена (404 person, 409 терминальный) |
| DELETE | `/work-permits/{id}/members/{member_id}` | убрать члена |
| GET | `/work-permits/{id}/readiness` | предпросмотр гейта (block+warn) |
| POST | `/work-permits/{id}/issue` | выдать (гейт; 409 `WORK_PERMIT_BLOCKED` со списком; FSM 409) |
| POST | `/work-permits/{id}/suspend` | приостановить |
| POST | `/work-permits/{id}/resume` | возобновить |
| POST | `/work-permits/{id}/close` | закрыть |
| POST | `/work-permits/{id}/cancel` | аннулировать |
| POST | `/work-permits/{id}/extend` | продлить `planned_end` |
| GET | `/work-permits/{id}/events` | журнал событий |

`WorkPermitTransitionError`→409 `WORK_PERMIT_TRANSITION_INVALID`; `WorkPermitBlocked`→409 `WORK_PERMIT_BLOCKED` (с `details.violations`). `@audit_operation` на create/update/issue/suspend/resume/close/cancel/extend.

### 3.7 Миграция `wp01`
- `down_revision = "20260615_prm01_permit_status_varchar"` (стек поверх Срез-1). Перед написанием — `alembic heads` подтвердить единственный head `prm01`.
- Создаёт три таблицы с tenant_id + индексами + FK (PG); SQLite-совместимо. Имена литералами; honest downgrade (drop в обратном порядке FK→таблицы).

## 4. Тесты
- `backend/tests/test_work_permit_lifecycle.py` — FSM (переходы, неизвестные статусы, валидация work_type/role).
- `backend/tests/test_wp01_work_permit_migration.py` — guard (цепочка к `prm01`, литералы, shape моделей: status VARCHAR(32)).
- `tests/test_work_permit_service.py` — create/update/add-member/issue/suspend/resume/close/extend (FSM-гейты, события пишутся).
- `tests/test_work_permit_admission.py` — гейт: просроченный личный `Permit` блокирует выдачу; чистая бригада проходит; warn не блокирует.
- `tests/api/test_work_permits_api.py` — CRUD + действия + 409 (FSM/blocked) + 404 + `/readiness` + изоляция тенантов.

## 5. Локальный прогон (Win/Py3.13/.venv)
PowerShell→file, итог по EXIT-коду (см. [[py313_win_pytest_invocation]]); канон Py3.12 = CI. App-fixture тесты медленные — `--timeout` щедрый, фоном. Не гонять полный suite. **Внимание** ([[subagent_stash_hazard]]): субагенты могут запарковать незакоммиченные правки — проверять `git status`/`git stash list` после прогонов.

## 6. Декомпозиция (план будет крупным)
Срез большой (ядро+гейт+mobile+фото). План — ~9 задач TDD: (1) lifecycle, (2) модели+миграция wp01+guard, (3) сервис документа+члены+события, (4) гейт допуска, (5) схемы, (6) CRUD+члены API, (7) действия issue/suspend/resume/close/cancel/extend API, (8) readiness+events API, (9) регрессия+handoff. Каждая — implementer + spec-review + quality-review.
