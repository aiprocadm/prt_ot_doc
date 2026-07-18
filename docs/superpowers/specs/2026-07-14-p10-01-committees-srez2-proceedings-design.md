# P10-01 Комитеты, срез-2 — ядро заседаний (кворум/голосование/протоколы) — design spec

- **Дата:** 2026-07-14
- **Статус:** approved (brainstorming через AskUserQuestion — 4 решения + одобрение дизайна и варианта A)
- **Ветка:** `feat/p10-01-committees-srez2-proceedings` от `main` (head после PR #740, RBAC-sweep влит; P10-07 дашборды/report-builder влиты PR #733/#732).
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B.17 → `PLATFORM_VNEXT_UPGRADE_SPEC.md` (комитеты/комиссии/заседания). Roadmap: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` строка P10-01 → «Остаётся (срез-2): голосование/кворум, приглашения, KPI-дашборд, журнал/нумерация протоколов, проекция задач в Command Center».
- **Head миграций:** `20260710_rb01_report_definition` (цепочка `…wa09 → wh01 → med03 → rb01`). Новая миграция `cmt02` — от `rb01`.

## 1. Контекст (сверка код↔ТЗ)

Уже в `main` (срез-1, PR #695):
- **Модели** `backend/app/models/committees.py`: `Committee` (kind osms/pb/commission_training/commission_investigation/other, soft-delete), `CommitteeMember` (роли chair/secretary/member, БЕЗ soft-delete — физический DELETE через remove_member), `CommitteeMeeting` (статус planned/held/cancelled, soft-delete), `CommitteeAgendaItem`, `CommitteeDecision`, `CommitteeDecisionTask` (open/in_progress/done, `is_overdue`-проекция).
- **Lifecycle** `domains/committees/lifecycle.py` (чистые функции): переходы заседания planned→held/cancelled, held→cancelled; `ensure_meeting_held` — решения только на held; `is_task_overdue`.
- **Service** `domains/committees/service.py`: `task_to_read` (overdue-проекция), `build_protocol` (meeting + decisions + tasks; принимает уже-загруженные ORM-строки для юнит-тестируемости без сессии).
- **API** `api/routes/committees.py`: полный CRUD (15 эндпоинтов), `GET /meetings/{mid}/protocol`. RBAC — `abac(_tenant_resource_id, required_roles=["admin"])` router-level. Фичефлаг `committees` default-off (`_require_committees_enabled`, 404 при выключенном). ETag+tenant-iso на списках.
- **Frontend** `pages/committees/CommitteesPage.tsx` + `api/committees.ts`: **read-only** страница (комитеты → заседания → протокол). Ни одной write-формы, RBAC на фронте НЕ гейтится.
- **Demo-seed** `_seed_committees_demo` (`services/demo_bootstrap.py:610`): комитет «Комитет по охране труда» + заседание + повестка + решение + задача. **Членов НЕ сеет** (кворум в UI сейчас проверить не с чем).

**Дыры относительно ТЗ (срез-2):** нет присутствия/кворума, нет голосования (решения — только текст), протоколы не нумеруются (нет журнала), заседание переходит в held без гейта кворума, фронт не умеет ничего создавать/проводить/голосовать.

## 2. Решения (зафиксированы пользователем через AskUserQuestion)

1. **Срез = P10-01 срез-2** (из кандидатов `[v1.1]`: §12.4 бюджет, P10-10 rules-engine, P10-07-хвост).
2. **Объём = «ядро заседаний»**: кворум + голосование + нумерация/журнал протоколов + write-UI. Приглашения / KPI-дашборд / проекция в Command Center — осознанно в срез-3.
3. **Правило кворума = простое большинство, фиксированное**: кворум = присутствует строго больше половины действующих членов; решение «принято» если голосов «за» > «против» (воздержавшиеся идут в кворум, но не в подсчёт), иначе «отклонено». Без пер-комитетной настройки.
4. **Нумерация = авто при проведении**: номер присваивается в момент перехода заседания в `held`, формат `N/ГГГГ`, сквозная per-комитет в пределах года (`N = max+1`), гонка закрыта unique-констрейнтом.
5. **Архитектура = вариант A** (отдельные таблицы attendance/votes + иммутабельный снапшот кворума на заседании; итог голосования вычисляется на лету).
6. **Поддерживающий write-UI включаем** — формы создания комитета/члена/заседания/решения/задачи (API уже есть с срез-1, не было пикселей) → срез-1-страница становится полностью рабочей.

## 3. Не-цели (осознанно отложено в срез-3)

- Приглашения на заседание (email/notification членам).
- KPI-дашборд комитетов (заседаний проведено, решений, просроченных задач, явка).
- Проекция задач комитетов в Command Center (search-index / dashboard-snapshot).
- Настраиваемый порог кворума / квалифицированное большинство (2/3).
- Self-service голосование (сейчас секретарь/админ заносит голоса за членов — модель бумажного протокола).
- RBAC-роли «секретарь»/«председатель» на роутере (остаётся admin-only, консистентно с срез-1).
- Печатная форма протокола DOCX/PDF (журнал есть; рендер — follow-up).
- Изменение состава участников голосования по решению (голосуют все присутствующие члены).

## 4. Модель данных — миграция `cmt02` (аддитивная, от `rb01`)

**Новый enum** `VoteChoice` (native_enum, `.value`-метки, `name="votechoice"`):
- `FOR = "for"` · `AGAINST = "against"` · `ABSTAIN = "abstain"`.

**Новая таблица `committee_meeting_attendance`** (`TenantBaseModel`, без soft-delete):
- `meeting_id` → `committee_meeting.id` ondelete CASCADE, index.
- `person_id` → `person.id` ondelete RESTRICT, index (паттерн `CommitteeMember.person_id`).
- `present` bool NOT NULL default True.
- unique `(tenant_id, meeting_id, person_id)` — `uq_committee_attendance`.

**Новая таблица `committee_decision_vote`** (`TenantBaseModel`, без soft-delete):
- `decision_id` → `committee_decision.id` ondelete CASCADE, index.
- `person_id` → `person.id` ondelete RESTRICT, index.
- `choice` VoteChoice NOT NULL.
- unique `(tenant_id, decision_id, person_id)` — `uq_committee_vote`.

**Новые колонки `committee_meeting`** (все nullable — заполняются при проведении):
- `held_at` DateTime(tz) — фактический момент проведения.
- `protocol_seq` Integer — порядковый номер протокола в пределах комитета/года.
- `protocol_year` Integer — год присвоения.
- `members_total` Integer — снапшот числа действующих членов на момент проведения.
- `present_count` Integer — снапшот числа присутствовавших.
- `quorum_met` Boolean — снапшот факта кворума.
- Partial unique index `(tenant_id, committee_id, protocol_year, protocol_seq) WHERE protocol_seq IS NOT NULL` — `uq_committee_protocol_no` (PG16 partial-index, паттерн `wa07`).

**Денормализация — обоснование:** снапшот кворума иммутабелен после `held` → протокол/журнал показывают исторически верные числа независимо от последующих изменений состава. Итог голосования по решению **не** денормализуем (голоса добавляются по ходу заседания; вычисляем на лету в проекции, как срез-1 считает `is_overdue`).

## 5. Чистые правила — расширяем `domains/committees/lifecycle.py`

Без доступа к БД (юнит-тестируемо, детерминизм через параметры — паттерн `is_task_overdue(..., today)`):

- `is_quorum(members_total: int, present_count: int) -> bool` → `present_count * 2 > members_total`; `members_total <= 0 → False`.
- `tally_votes(choices: Iterable[VoteChoice]) -> tuple[int,int,int]` → `(for, against, abstain)`.
- `DecisionOutcome(str, enum)` = `CARRIED="carried"` / `REJECTED="rejected"` (проекционный enum, НЕ в БД).
- `decision_outcome(votes_for: int, votes_against: int) -> DecisionOutcome` → `CARRIED` если `for > against`, иначе `REJECTED` (ничья → REJECTED).
- `next_protocol_seq(existing_seqs: Iterable[int]) -> int` → `max(existing, default=0) + 1`.
- `validate_hold(current: MeetingStatus, quorum_met: bool) -> None` → переиспользует `validate_meeting_transition(current, HELD)`, затем если `not quorum_met` → `MeetingTransitionError` (кворум-гейт). Роут маппит в 409.
- `ensure_can_vote(meeting_status: MeetingStatus) -> None` → голос только на `held` (иначе `MeetingTransitionError`).

## 6. API — новое поверх срез-1 (`api/routes/committees.py`, `schemas/committees.py`)

Все под тем же router-level `abac(required_roles=["admin"])` + фичефлаг `committees`. Новые коды ошибок в `error_type="committees"`.

- **`GET /committees/meetings/{mid}/attendance`** → `AttendanceRead[]` (person_id, present). Для UI-чекбоксов.
- **`PUT /committees/meetings/{mid}/attendance`** — bulk-замена: тело `{items: [{person_id, present}]}`. Валидация: каждый `person_id` — действующий член комитета заседания (иначе 422 `COMMITTEE_NOT_A_MEMBER`); заседание в статусе `planned` (после проведения присутствие иммутабельно → 409). Upsert по `(meeting, person)`.
- **`PATCH /committees/meetings/{mid}`** (расширяем существующий) — при `status → held`:
  1. `validate_meeting_transition` (как сейчас).
  2. Считаем `members_total` = число **DISTINCT `person_id`** среди `CommitteeMember` комитета (человек с двумя ролями — chair+member — это одна «голова» для кворума; unique-констрейнт члена `(tenant, committee, person, role)` допускает 2 строки на персону); `present_count` = число attendance-строк с `present=True` (attendance уникален по `(meeting, person)` → задвоения нет).
  3. `is_quorum(...)` → нет кворума → 409 `COMMITTEE_QUORUM_NOT_MET` (заседание остаётся `planned`).
  4. Присвоение номера: `protocol_year = held_at.year`; `protocol_seq = next_protocol_seq(seqs комитета за год)`; при `IntegrityError` на unique → 409 `COMMITTEE_PROTOCOL_CONFLICT`.
  5. Ставим `held_at`, снапшот `members_total/present_count/quorum_met=True`.
  - `held_at`/год — через инъектируемый `now` (для тестов), дефолт `datetime.now(tz=utc)`.
- **`POST /committees/decisions/{did}/votes`** — upsert голоса `{person_id, choice}`. Валидация: `ensure_can_vote(meeting.status)` (409 `COMMITTEE_DECISION_NOT_HELD`); `person` присутствовал (`present=True`) → иначе 409 `COMMITTEE_VOTER_ABSENT`. Возвращает `VoteRead`.
- **`GET /committees/decisions/{did}/votes`** → `DecisionVoteSummary` (список голосов + tally for/against/abstain + outcome).
- **`GET /committees/meetings/{mid}/protocol`** (расширяем `ProtocolRead`): добавляем в `meeting`-проекцию `protocol_no` (строка `N/ГГГГ` или null), `members_total`/`present_count`/`quorum_met`; по каждому решению — `votes_for/against/abstain` + `outcome` + список голосов.
- **`GET /committees/protocols`** — **журнал протоколов**: пронумерованные проведённые заседания (`protocol_seq IS NOT NULL`), опц. фильтр `committee_id`, сортировка `protocol_year desc, protocol_seq desc`, пагинация (limit/offset) + ETag+304 (паттерн `list_committees`). Элемент: committee_id, committee_name, protocol_no, held_at, decisions_count, present_count/members_total.

**Схемы:** `AttendanceItem`/`AttendanceRead`/`AttendanceBulkUpdate`, `VoteCreate`/`VoteRead`/`DecisionVoteSummary`, расширенные `MeetingRead` (+protocol_no/снапшот) и `ProtocolDecision` (+tally/outcome/votes), `ProtocolJournalItem`/`ProtocolJournalPage`. `protocol_no` — computed в схеме из seq+year (без денормализации строки в БД).

## 7. Frontend — `CommitteesPage.tsx` + `api/committees.ts`

**API-клиент** (`committees.ts`): + `getAttendance`/`putAttendance`, `castVote`/`getVotes`, `listProtocols`, расширенные типы `Meeting`/`Protocol`.

**Ядро заседаний (UI):**
- Секция «Члены комитета» (список + форма добавления {person picker, роль} + удаление).
- Секция «Присутствие» на выбранном `planned`-заседании: чекбоксы членов → «Сохранить присутствие» (PUT). Индикатор кворума (present/total, «кворум есть/нет»).
- Кнопка «Провести заседание» → PATCH held; при 409 `COMMITTEE_QUORUM_NOT_MET` — понятная ошибка. После проведения — номер протокола + снапшот кворума, присутствие/проведение блокируются.
- По каждому решению held-заседания: голосование (на присутствующего члена — за/против/воздержался), tally + бейдж «Принято»/«Отклонено».
- Секция «Журнал протоколов» (список пронумерованных протоколов, ссылка на протокол).

**Поддерживающий write-UI** (API есть с срез-1): формы создания комитета, заседания, решения, задачи; смена статуса задачи. Делает срез-1-страницу полностью рабочей.

**RBAC на фронте** — НЕ гейтим (консистентно с срез-1; роутер admin-only и так вернёт 403 не-админу → ошибкой секции). `permissions.ts` не трогаем.

**Person picker** — переиспользуем существующий паттерн выбора персоны (typeahead, первые N; серверный typeahead — follow-up, как в медосмотрах).

## 8. Demo-seed (`_seed_committees_demo`)

Расширить идемпотентно: добавить 3-4 `CommitteeMember` (chair/secretary/member) к демо-комитету; отметить присутствие; провести заседание (кворум есть) → присвоить `1/ГГГГ`; добавить голоса по демо-решению (принято) — чтобы журнал/протокол/голоса были видны в demo-тенанте из коробки.

## 9. Тест-план

**Backend unit (чистые функции, без сессии):**
- `is_quorum`: 0 членов → нет; ровно половина (2 из 4) → нет; половина+1 (3 из 4) → да; все → да.
- `tally_votes` / `decision_outcome`: for>against → carried; ничья (for==against) → rejected; только abstain → rejected.
- `next_protocol_seq`: пусто → 1; [1,2] → 3; изоляция по (комитет, год) — проверяется на уровне запроса в API-тесте.
- `validate_hold`: planned+кворум → ok; planned без кворума → error; held→held → error.

**Backend API (async, tenant-iso):**
- attendance: PUT валидирует членство (не-член → 422); после held → 409; чтение отражает записанное.
- проведение: успех → номер `1/ГГГГ` + снапшот `quorum_met=True`; без кворума → 409, статус остаётся planned; повторный held → 409; изоляция нумерации (два комитета → у каждого `1/ГГГГ`; второе заседание того же комитета → `2/ГГГГ`).
- голоса: upsert (повторный голос того же лица обновляет choice, не дублирует); голос не-присутствующего → 409; голос на non-held решении → 409.
- протокол: содержит номер/снапшот/tally/outcome.
- журнал: только пронумерованные; сортировка; фильтр по committee_id; tenant-iso; ETag/304.

**Frontend (vitest):** api-клиент (новые методы) + страница (чекбоксы присутствия, состояние кнопки проведения при нет/есть кворума, бейджи голосования, журнал). AppRouterSmoke — маршрут `/committees` не меняется (журнал — секция на той же странице).

**Гейты (порядок как в прошлых срезах):**
1. Backend-регресс батчами ≤5 файлов (PowerShell, ОДИН прогон, timeout 600000): новые unit + API + demo-seed + смежные committees-тесты срез-1.
2. `ruff` + `black` clean.
3. **PG16-гейт** `scripts/ci/local_gate.py --db-only`: миграция `cmt02` up/down round-trip (native enum `votechoice` + partial unique index) на реальном PG16.
4. **OpenAPI baseline** пере-снять (+ роуты attendance/votes/protocols + расширенные схемы); `check_openapi_snapshot.py` compare `✓ ARCH-4 unchanged`.
5. Frontend: точечный vitest → полный `vitest run` (не параллелить с pytest; красный полного прогона перепроверять повтором — контеншн-флейк) → `tsc --noEmit` → `vite build`.

## 10. Риски / грабли

- **`CommitteeMember` без soft-delete** (физический DELETE). Attendance/votes ссылаются на `person_id` (не на `committee_member.id`) → история присутствия/голосов переживает удаление члена из состава. Кворум считается по ТЕКУЩИМ членам на момент проведения (снапшот фиксирует число).
- **Задвоение члена по ролям** — unique `(tenant, committee, person, role)` допускает одну персону в двух ролях (chair+member). `members_total` и любой подсчёт «членов» = COUNT(DISTINCT person_id), иначе кворум и явка задваиваются. Юнит/API-тест на персону с двумя ролями.
- **Enum `FOR`** — `for` зарезервированное слово Python; имя мембера `FOR` валидно, коллизии нет (это идентификатор атрибута, не ключевое слово в позиции стейтмента).
- **Гонка номера** — single-writer админ, но unique-констрейнт + 409-обработка обязательны (без ретрая в срез-2).
- **PG16 partial unique index** `WHERE protocol_seq IS NOT NULL` — писать через `postgresql.ENUM`/`op.create_index(..., postgresql_where=...)` (правило enum-миграций: не `sa.Enum`); проверить SQLite-совместимость conftest (`metadata.create_all` — partial index на SQLite игнорируется/поддерживается частично; API-тесты идут на SQLite, PG16-специфику проверяет только db-гейт).
- **Операционка (из прошлых handoff'ов):** worktree для имплементации; PowerShell для pytest (Git-Bash сегфолтит); `git -C <абсолютный путь>`; полный vitest не параллелить; cold-import >120s → pytest timeout 600000 ОДИН прогон.
- **Мульти-сессионный git-hazard** (память `git-multisession-hazard`): коммитить атомарно `git commit -- <paths>`, пушить/мержить своевременно, работать в изолированном worktree.

## 11. Порядок реализации (для writing-plans)

1. Модель + миграция `cmt02` (2 таблицы, enum, 6 колонок, partial index) + PG16-гейт.
2. Чистые правила в `lifecycle.py` + unit-тесты.
3. Схемы + service-проекции (tally/outcome/protocol-расширение/журнал).
4. API-эндпоинты (attendance/hold-расширение/votes/protocols) + API-тесты.
5. Demo-seed расширение.
6. Frontend API-клиент + типы.
7. Frontend UI (ядро заседаний + поддерживающий write-UI) + vitest.
8. Гейты: OpenAPI baseline, полный vitest, tsc, build; docs (handoff/CHANGELOG/roadmap).
