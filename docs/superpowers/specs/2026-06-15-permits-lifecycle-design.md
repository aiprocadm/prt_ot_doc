# Личные допуски (Permit): запись + жизненный цикл — дизайн

**Дата:** 2026-06-15
**Контур:** Допуски / наряды-допуски (ТЗ раздел B.15, vNext §16). **Срез-1 из 2.**
**Ветка:** `feat/permits-lifecycle`
**Статус до среза:** Модель `Permit` существует (`backend/app/models/models.py:1413`) как тонкая запись личного допуска: `person_id`, `position_id`, `permit_type`, `issued_at`, `valid_until`, `status` (нативный enum `PermitStatus`: active/expired/revoked). Записи **создаются автоматически** при выдаче удостоверения обучения (`backend/app/domains/training/service.py:251-265`), **читаются** в карточке сотрудника (`backend/app/services/employee_card.py:479-537`), в календаре (`backend/app/services/calendar_aggregator.py:662-674`) и в правилах качества данных (`backend/app/modules/data_quality/rules.py:374-383`). **Чего нет:** API на запись (создать/править/продлить/отозвать), доменный сервис и FSM, материализация просрочки, тесты. Личный допуск ≠ формальный наряд-допуск §16 — последний строится отдельным Срез-2.

## 1. Цель среза

Превратить `Permit` из «read-only записи, рождающейся только из обучения» в полноценно управляемую сущность: ручной CRUD, явный жизненный цикл (продление, отзыв, авто-просрочка), правдивый статус для календаря и data_quality. Объём — личные допуски; формальный наряд-допуск на работы повышенной опасности (бригада, зоны, меры, open/close, фотофиксация — vNext §16) — **Срез-2**.

### Не-цели среза
- Формальный наряд-допуск §16 (новая модель `WorkPermit`, бригада, FSM open/close, mobile, фотофиксация).
- Фронтенд (страница управления допусками) — отдельная фронт-добивка.
- Каталог типов допусков (`permit_type` остаётся свободным текстом — YAGNI).
- Изменение авто-создания допусков из обучения по сути (только адаптация под строковый статус).

## 2. Решение по статусу (анти-грабли)

`Permit.status` переводится из нативного PG-enum `Enum(PermitStatus)` в `VARCHAR(32)` — единообразно с недавними срезами СИЗ (`ppeissue.status` → VARCHAR, миграция sz01) и подрядчиков (VARCHAR `doc_type`/`scope`). Это:
- снимает класс «ORM↔PG enum-label parity» (известные грабли проекта),
- упрощает добавление будущих статусов без `ALTER TYPE ADD VALUE`,
- делает строковый статус естественным для FSM-модуля.

Канонические строковые значения сохраняются прежними: `"active"`, `"expired"`, `"revoked"`. Python-константы остаются в `PermitStatus`-подобном виде, но как строковые константы (по образцу `domains/ppe/lifecycle.py`: `ISSUE_STATUS_*`).

## 3. Архитектура

Зеркалит паттерн `domains/ppe` и `domains/contractors`:

```
backend/app/domains/permits/
  __init__.py          # реэкспорт публичных функций/констант
  lifecycle.py         # чистый FSM + статусы (без I/O)
  service.py           # session-aware операции (create/update/extend/revoke + tick)
backend/app/api/routes/permits.py   # CRUD + операции
backend/app/schemas/permit.py       # Pydantic-схемы
backend/app/migrations/versions/20260615_prm01_permit_status_varchar.py
```

### 3.1 Чистый `lifecycle.py`
- Константы: `PERMIT_STATUS_ACTIVE = "active"`, `_EXPIRED = "expired"`, `_REVOKED = "revoked"`; набор `PERMIT_STATUSES`.
- `_TRANSITIONS`: `active → {expired, revoked}`; `expired → {active}` (только через продление/ре-валидацию); `revoked` — терминальный.
- `assert_transition(current, target)` — поднимает `ValueError` на недопустимый переход.
- `is_expired(status, valid_until, today) -> bool` — `status == active and valid_until is not None and valid_until < today`.
- `due_status(status, valid_until, today) -> str` — возвращает целевой статус для авто-просрочки (`expired`, если `is_expired`, иначе текущий).

### 3.2 Сервис `service.py` (session-aware)
- `create_permit(session, tenant_id, *, person_id, permit_type, issued_at, valid_until, position_id) -> Permit` — валидирует существование person (404), `position_id` опционален; стартовый статус через `due_status` (если уже просрочен — сразу `expired`).
- `update_permit(session, tenant_id, permit_id, *, permit_type?, valid_until?, position_id?) -> Permit` — правка только если статус `active` (иначе 409 `permit_not_active`).
- `extend_permit(session, tenant_id, permit_id, *, valid_until) -> Permit` — продление: для `active` обновляет `valid_until`; для `expired` выполняет переход `expired → active` (ре-валидация) с новым сроком; `revoked` → 409.
- `revoke_permit(session, tenant_id, permit_id) -> Permit` — `active → revoked` через `assert_transition`; повторный отзыв → 409.
- `expire_due(session, tenant_id=None) -> int` — материализация: переводит все `active` c `valid_until < today` в `expired`, возвращает счётчик (используется beat'ом).
- Все операции tenant-scoped, soft-deleted записи (если появятся) исключаются.

### 3.3 API `routes/permits.py`
Базовый префикс `/permits`. Отдельный feature-gate не вводим (YAGNI) — только ABAC по фактическому списку ролей из `ppe.py`/`contractors.py`:
- read-роли: `admin`, `owner`, `hse_head`, `hr`, `line_manager`;
- write-роли: `admin`, `owner`, `hse_head`.

Точные имена ролей и хелперы (`ReaderAccess`/`WriterAccess`) взять из существующих роут-модулей, не выдумывать.

| Метод | Путь | Назначение | Коды |
|---|---|---|---|
| GET | `/permits` | список с фильтрами `person_id`, `status`, `expired_only`, пагинация | 200 |
| POST | `/permits` | создать допуск | 201, 404 (person), 422 |
| GET | `/permits/{id}` | деталь | 200, 404 |
| PATCH | `/permits/{id}` | правка активного | 200, 404, 409 |
| POST | `/permits/{id}/extend` | продлить (новый `valid_until`) | 200, 404, 409 |
| POST | `/permits/{id}/revoke` | отозвать | 200, 404, 409 |

Ответы — `PermitRead`; ошибки — структурированный контракт проекта (как в `ppe.py`: `code`/`message`).

### 3.4 Схемы `schemas/permit.py`
`PermitCreate` (person_id, permit_type, issued_at?, valid_until?, position_id?), `PermitUpdate` (опциональные permit_type/valid_until/position_id), `PermitExtend` (valid_until), `PermitRead` (все поля + `is_expired: bool` вычисляемый), `PermitPage` (items + total).

### 3.5 Миграция `prm01`
- `down_revision` = текущий головной ревижн (определить `alembic heads` перед написанием; в дереве смешаны стили `revision =`/`revision:`).
- Upgrade: `ALTER COLUMN permit.status TYPE VARCHAR(32) USING status::text` (PG); под SQLite — batch-alter. Дроп осиротевшего enum-типа `permitstatus`, если он более нигде не используется (проверить через grep по моделям).
- Downgrade: обратная конверсия в enum (guard: если есть значения вне {active,expired,revoked} — поднять понятную ошибку, по образцу `ed01`).
- Round-trip-safe; имена таблиц/типов — литералами (анти-грабли AST-аудита).

### 3.6 Beat `permits.expiry.tick`
- Зеркало `ppe.expiry.tick` (`backend/app/tasks/_core.py` + расписание в `backend/app/services/celery_app.py`).
- Ежедневно вызывает `expire_due(session)` по всем тенантам; логирует число переведённых.
- Идемпотентно (повторный прогон в тот же день ничего не меняет).

## 4. Адаптация существующих читателей

`status` становится строкой — сравнения `== PermitStatus.ACTIVE` заменяются на строковую константу `PERMIT_STATUS_ACTIVE`:
- `backend/app/services/employee_card.py` (`_build_permits`, счётчики active/expired).
- `backend/app/services/calendar_aggregator.py` (фильтр активных допусков для событий).
- `backend/app/modules/data_quality/rules.py` (`ExpiredPermitsRule`).
- `backend/app/domains/training/service.py` (авто-создание допуска: присвоить строковый статус через `due_status`).
- `backend/app/schemas/employee.py` (поле `status` уже строковое в DTO — проверить тип).

Поведение для конечного пользователя не меняется; меняется только тип хранения статуса.

## 5. Тесты

- `backend/tests/test_permit_lifecycle.py` — чистый FSM (переходы, `is_expired`, `due_status`, недопустимые переходы → ValueError).
- `backend/tests/test_prm01_permit_status_migration.py` — guard миграции (цепочка к единственному head, литералы имён, round-trip, конверсия типа).
- `tests/api/test_permits_api.py` — CRUD, 404 (person/permit), 409 (правка/отзыв не-active), фильтры (person_id, status, expired_only), ABAC (read/write роли).
- `tests/test_permits_expire_tick.py` — beat: просроченный active → expired; revoked/уже-expired не трогаются; счётчик корректен.
- Регрессия читателей: существующие тесты карточки сотрудника / календаря / data_quality остаются зелёными после строковой адаптации.

## 6. Локальный прогон (Win/Py3.13/.venv)

Через PowerShell с редиректом в файл (см. `py313_win_pytest_invocation`):
`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest <путь> -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"` — затем читать `_t.txt`. Канон Py3.12 = CI; расхождение версии указывать в отчёте, не абортить.

## 7. Контракт демо-данных

Опционально: расширить `demo_bootstrap` примером ручного допуска (не из обучения), чтобы фильтр `expired_only` и операции были демонстрируемы. Низкий приоритет — можно в конце среза.
