# Дизайн: Наряд-допуск на высоте (782н) — Ф3a «журнал эксплуатации»

- **Дата:** 2026-06-18
- **Контур:** Наряды-допуски §16, эталон «работа на высоте» (Приказ Минтруда № 782н).
- **Этап:** Ф3a из программы Ф1→Ф4. Ф1 (модель+экран) **влит** (PR #669). Ф2 (целевой инструктаж + подписи ПЭП) — PR #671 (открыт). **Ф3 разделён на два среза:** Ф3a — журнал эксплуатации (ежедневный допуск + журнал продлений + смена состава), **Ф3b** — закрытие наряда с подписями (отдельная спека, расширяет Ф2). Ф4 — печатный бланк.
- **Полнота стека:** Ф3a — **full-stack** (новая таблица допуска + колонка `meta` у событий + сервис + миграция + API + фронтенд). Без подписей.
- **Ветка:** `feat/work-permits-782n-ops-journal` (стек **поверх Ф2** `feat/work-permits-782n-signatures`, т.к. правит те же фронтенд-файлы и миграции цепляются последовательно).
- **Источники:** [Приказ 782н — КонсультантПлюс](https://www.consultant.ru/document/cons_doc_LAW_371453/) — раздел «ежедневный допуск к работе и её окончание», продление наряда, изменение состава бригады.

## 1. Контекст и цель

После Ф1/Ф2 наряд можно завести по форме, провести по FSM, провести инструктаж и собрать подписи. Но **операционная жизнь наряда в статусе `issued`** не отражена: для многодневных работ нет ежедневного допуска к работе; продление (`extend`) меняет дату, но журнал не хранит «было→стало»; смена состава бригады на уровне сервиса возможна, но **не журналируется** и в UI закрыта (только `draft`). Ф3a даёт **единый журнал эксплуатации**: ежедневный допуск (таблица 782н), структурный журнал продлений и смену состава — всё поверх существующих `WorkPermitEvent` и `WorkPermitMember`, без изменения FSM.

## 2. Объём

**В объёме (Ф3a):**
- **Ежедневный допуск** к работе — новая таблица (дата, время начала/окончания смены, кто допустил, отметка). Только для наряда в статусе `issued`.
- **Журнал продлений** — `extend` сохраняет `{old_end, new_end}` в `meta` события `extended`; лента показывает «продлён с X до Y».
- **Смена состава бригады** в `issued`/`suspended` — `add_member`/`remove_member` пишут события (`member_added`/`member_removed`, `meta={person_id, role}`); UI открывает редактирование бригады вне `draft`.
- Frontend: панель ежедневного допуска + обогащённая лента событий + редактирование бригады в `issued`.
- Только роль `admin`.

**Вне объёма:**
- **FSM не меняется** — допуск/продление/смена состава **не меняют статус** наряда.
- Подписи (закрытие с подписями — Ф3b; подписи инструктажа/наряда — Ф2).
- Печатный бланк (Ф4).
- Уведомления о просрочке смены, гео/фото допуска — отдельные мобильные сценарии.

## 3. Аудитория и права

- Роль `admin`. Backend `/work-permits` уже гейтит `required_roles=["admin"]`.
- Фронтенд: переиспользуем коды Ф1 — `work_permit.view` (просмотр), `work_permit.manage` (допустить на смену, изменить состав). Новых кодов нет.

## 4. Модель данных (backend)

Аддитивная миграция **`wp04`** (цепочка от истинного head — `wp03` Ф2, если стек; определить в плане; имена таблиц литералами; honest downgrade).

**Новая таблица `work_permit_daily_admission`** (модель `WorkPermitDailyAdmission`, `TenantBaseModel`):

| Колонка | Тип | Назначение |
|---|---|---|
| `work_permit_id` | FK→`work_permit.id` (CASCADE), not null, index | наряд |
| `admission_date` | Date, not null | дата смены |
| `start_at` | DateTime(tz), null | время начала работы |
| `end_at` | DateTime(tz), null | отметка окончания смены |
| `admitted_by_person_id` | FK→`person.id` (SET NULL), null | кто допустил (допускающий) |
| `note` | Text, null | примечание |

**Новая колонка у `work_permit_event`:** `meta` — JSON, nullable. Семантика по `event_type`:
- `extended` → `{"old_end": iso|null, "new_end": iso|null}`;
- `member_added` / `member_removed` → `{"person_id": str, "role": str}`.

**Новые типы событий** (`domains/work_permits/lifecycle.py::EVENT_TYPES`): добавить `admitted`, `member_added`, `member_removed` (`extended` уже есть).

## 5. Расширение сервиса (backend)

`backend/app/domains/work_permits/service.py`:
- **Ежедневный допуск:**
  - `create_admission(session, *, tenant_id, work_permit_id, admission_date, start_at?, end_at?, admitted_by_person_id?, note?)` — только если наряд в статусе `issued` (иначе `WorkPermitTransitionError`); пишет событие `admitted`.
  - `list_admissions(...)` — по наряду, сортировка по `admission_date`.
  - `update_admission(...)` — дозаполнить `end_at`/`note` (отметка окончания смены).
- **Смена состава:** `add_member`/`remove_member` — после изменения вызвать `_log(event_type="member_added"|"member_removed", meta={"person_id":..., "role":...})`; разрешены в `draft/issued/suspended`, блок в `closed/cancelled` (для `remove_member` добавить терминальный гейт, которого сейчас нет).
- **Продление:** `extend` — перед сменой `planned_end` запомнить старое значение, передать `meta={"old_end": iso(old), "new_end": iso(new)}` в `_log`.
- Хелпер `_log` расширяется параметром `meta: dict | None = None` (пишется в новую колонку).

## 6. API (backend, на `routes/work_permits.py`)

- `POST /work-permits/{id}/admissions` — создать ежедневный допуск (`admission_date`, `start_at?`, `end_at?`, `admitted_by_person_id?`, `note?`); 409 если наряд не `issued`.
- `GET /work-permits/{id}/admissions` — список допусков наряда.
- `PATCH /work-permits/{id}/admissions/{admission_id}` — отметить окончание/правку (`end_at`, `note`); допуск обязан принадлежать этому наряду (cross-permit guard, как в Ф2).
- Контракт `members`-эндпоинтов и `extend` не меняется — они теперь журналируют. `GET /events` отдаёт `meta` + новые типы.
- Схемы: `WorkPermitDailyAdmissionCreate/Update/Read`; `WorkPermitEventRead` получает `meta: dict | None`.

## 7. Архитектура фронтенда (паттерн карточки Ф1/Ф2)

| Файл | Назначение |
|---|---|
| `frontend/src/api/workPermits.ts` | + `listAdmissions/createAdmission/updateAdmission`. |
| `frontend/src/types/dto/workPermits.ts` | + `WorkPermitDailyAdmissionDto`; `WorkPermitEventDto` + `meta`. |
| `frontend/src/lib/workPermitVocab.ts` | + подписи новых типов событий (`admitted`/`member_added`/`member_removed`). |
| `frontend/src/features/work-permits/DailyAdmissionPanel.tsx` | таблица допусков + форма «Допустить на смену» (gated `issued` + manage) + «Закрыть смену» (`end_at`). |
| `frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx` | рендер `meta`: продление «с X до Y», смена состава «+ ФИО (роль)»; подписи новых типов. |
| `frontend/src/features/work-permits/BrigadeMembersPanel.tsx` | снять гейт «только draft» → редактирование в `issued`/`suspended`. |
| `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` | + монтаж панели допуска. |
| тесты | `DailyAdmissionPanel`/timeline-meta + гейт бригады в issued. |

ФИО — резолв `person_id → ФИО` через `/persons` (как в Ф1/Ф2).

## 8. Логика и состояния

- **Ежедневный допуск** доступен только для наряда `issued` (для `draft`/`suspended`/терминала — кнопка скрыта/disabled; backend гейтит). Несколько допусков на наряд (по дням) — 1:N.
- **Смена состава**: разрешена в `draft` (как в Ф1), `issued`, `suspended`; запрещена в `closed`/`cancelled`. Каждое изменение — событие в журнале.
- **Продление**: как в Ф1 (`issued`/`suspended`), но теперь с записью «было→стало».
- **FSM-переходы** (issue/suspend/resume/close/cancel) — **без изменений**.

## 9. Обработка ошибок

- Допуск при наряде не-`issued` → 409 `WORK_PERMIT_TRANSITION_INVALID` + понятный `toast`.
- Допуск/правка чужого наряда (cross-permit) → 404.
- Смена состава в терминале → 409.
- Загрузка панели упала → `ErrorState`; пусто → `EmptyState`.

## 10. Тестирование

- **Миграция `wp04` (guard):** цепочка от истинного head; таблица `work_permit_daily_admission` + колонка `meta` у `work_permit_event`; honest downgrade (drop column + drop table).
- **Сервис:** создание допуска; допуск только в `issued` (иначе ошибка); `add_member`/`remove_member` пишут события с `meta`; `remove_member` блок в терминале; `extend` пишет `{old_end, new_end}`.
- **API:** admission create→list→patch; cross-permit admission → 404; admission при не-`issued` → 409; member add в issued → событие в `/events` с `meta`; extend → событие с `meta`.
- **Frontend:** timeline рендерит `meta` (продление/смена состава); панель допуска (форма gated issued); бригада редактируема в issued.
- Прогон: Py3.12 если доступен, иначе доступный Python с отметкой версии (CLAUDE.md). Frontend: `npm --prefix frontend run test -- <file>` + `build`.

## 11. Критерии приёмки

1. Миграция `wp04` аддитивна, downgrade честный; guard зелёный.
2. Ежедневный допуск CRUD работает, гейт `issued`; cross-permit 404.
3. Продления показывают старую→новую дату; смена состава журналируется и видна; всё в едином журнале с `meta`.
4. Бригада редактируема в `issued`/`suspended`; **FSM-переходы не изменены**; admin-only.
5. Тесты (backend-контур + фронт-тесты) зелёные; сборка фронта без ошибок типов.

## 12. Открытые вопросы

Нет. Ежедневный допуск — отдельная таблица 1:N; продления/смена состава — обогащённые `WorkPermitEvent` через `meta` (JSON); закрытие с подписями вынесено в Ф3b.
