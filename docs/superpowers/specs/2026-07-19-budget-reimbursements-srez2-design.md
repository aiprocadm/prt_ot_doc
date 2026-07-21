# Заявки на возмещение СФР — кросс-доменный контур §12.4, срез-2 — Design

**Дата:** 2026-07-19
**Контур:** кросс-доменный §12.4 «Бюджетный контур» (ТЗ `PLATFORM_VNEXT_UPGRADE_SPEC.md §12.4`,
`TZ_FULL_UNIFIED.md:369` B.11 `[v1.1]`).
**Предшественник (влит в main, PR #753):** срез-1 «ядро» — бюджеты обучения/медосмотров/мероприятий,
справочник статей, журнал расходов `budget_expense`, план↔факт и разрезы
(спека `2026-07-17-budget-contour-core-design.md`). Этот срез закрывает единственный пункт,
явно вынесенный там в «Явно ВНЕ объёма (срез-2)».
**База ветки:** `main`@`4c31546f` (merge PR #764); ветка `feat/budget-srez2-reimbursements`.
**Head-миграция на старте:** `20260717_bg01_safety_budget_core` (единственный head). Новая
миграция `bg02` чейнится от неё.

> Документ написан **по факту реализации** (ретро-спека): срез-1 оставил заявки описанными двумя
> строками, отдельного design/plan-дока под срез-2 не заводилось. Здесь зафиксированы принятые
> решения и их причины, чтобы следующий агент не переоткрывал их заново.

## Цель

Дать организации рабочий процесс **возмещения расходов на охрану труда из СФР**: собрать заявку из
уже учтённых расходов журнала, провести её через согласование и зафиксировать факт выплаты.

Ключевой инвариант контура сохраняется дословно: **ничего не денормализуем**. Сумма состава заявки
всегда вычисляется из `budget_expense` join'ом — ни в строке состава, ни в заявке она не хранится.

## Принятые решения

1. **Заявка — самостоятельная сущность со своим жизненным циклом**, а не флаг на расходе. Один
   расход попадает в заявку строкой состава; заявка живёт по своему FSM независимо от расходов.
2. **`requested_amount` вводится вручную, а не выводится из состава.** Запрашиваемая сумма — это
   то, что организация просит у фонда; она сознательно может не совпадать с суммой привязанных
   расходов (частичное возмещение, лимиты фонда). Сумма состава показывается рядом справочно.
3. **FSM без возврата: `rejected` и `paid` терминальны.** Пересдача отклонённой заявки — это новая
   заявка, а не редактирование старой: у фонда это разные обращения, и история решений должна
   остаться неизменной.
4. **Правка только в `draft`.** После подачи заявка заморожена целиком — и реквизиты, и состав, и
   удаление. Иначе одобренная сумма относилась бы к неизвестно какому набору расходов.
5. **Отвязка расхода — жёсткий DELETE, а не soft-delete.** Уникальность пары
   `(reimbursement_id, expense_id)` объявлена **без** фильтра по `deleted_at` (конвенция
   `rules_engine`/`ReportDefinition`), поэтому soft-deleted строка навсегда блокировала бы повторную
   привязку того же расхода.
6. **Статус — `VARCHAR(32)` + whitelist в коде, без PG-enum** (анти-грабли конвенция `ppe.py`/
   `medical.py`, та же, что в `bg01`).
7. **Сид пишет статусы напрямую, минуя FSM.** Демо-данные должны показать заявки в разных
   состояниях с правдоподобными датами решений в прошлом; `run_action` не дал бы back-date
   `decided_at`, а сид — не пользовательская сессия.

## Архитектура

### Слой 1 — миграция `bg02` (аддитивная)

`backend/app/migrations/versions/20260719_bg02_budget_reimbursement.py`
`revision = "20260719_bg02_budget_reimbursement"`, `down_revision = "20260717_bg01_safety_budget_core"`.
Без backfill, без enum'ов. Downgrade — в FK-безопасном порядке (item → reimbursement).

**`budget_reimbursement`** — `title`, `status VARCHAR(32) server_default='draft'`,
`period_start/period_end Date`, `requested_amount Numeric(14,2)`, `approved_amount Numeric(14,2) NULL`,
`reference` (номер в СФР), `company_id → company.id ON DELETE SET NULL`, `decision_reason`,
`submitted_at` / `decided_at` / `paid_at`, `notes`.
Индексы: `(tenant_id)`, `(tenant_id, status)`.

**`budget_reimbursement_item`** — `reimbursement_id → budget_reimbursement.id ON DELETE CASCADE`,
`expense_id → budget_expense.id ON DELETE CASCADE`. **Суммы нет** (см. решение 2).
`UNIQUE (reimbursement_id, expense_id)`; индексы `(tenant_id)`, `(tenant_id, reimbursement_id)`.

### Слой 2 — модели

`backend/app/models/budget.py`: `BudgetReimbursement` (:90) и `BudgetReimbursementItem` (:119),
обе `TenantBaseModel + SoftDeleteMixin`.

### Слой 3 — FSM `reimbursement_lifecycle.py`

Чистый модуль без I/O и без SQLAlchemy — зеркало `app/domains/work_permits/lifecycle.py`.

```
draft ──submit──► submitted ──approve──► approved ──pay──► paid
                       └────reject────► rejected
```

`EDITABLE_STATUSES = {draft}`. Нарушение перехода и правка вне черновика — один класс
`ReimbursementTransitionError` → **409** `REIMBURSEMENT_TRANSITION_INVALID`.

### Слой 4 — сервис `reimbursement_service.py`

Сервис **ничего не коммитит** — транзакцией владеет роутер (конвенция среза-1).

- `aggregate_items()` — `item_count` и `items_amount` одним join'ом к `budget_expense`;
  soft-deleted расходы из суммы исключаются, но строка состава остаётся (осознанно: история
  заявки не должна меняться задним числом от удаления расхода).
- Tenant-валидация **всех** client-supplied FK (`_validate_company`, проверка расхода в `add_item`) —
  класс багов PR #749–751. Чужой тенант отдаёт **422 `unknown_*`**, а не 404: иначе ответ
  различал бы «нет такого» и «есть, но не ваш».
- Explicit-null guard `_REIMBURSEMENT_NON_NULLABLE` → `invalid_field_null` (конвенция `rules_engine`).
- Период на PATCH перепроверяется на **слитых** значениях (хранимое + входящее) → `period_invalid`.
- Решения: `approved_amount` по умолчанию = `requested_amount`; больше запрошенной →
  `approved_amount_invalid`; отклонение без причины → `decision_reason_required`; подача пустой
  заявки → `reimbursement_empty`.

Typed-коды **422**: `unknown_company`, `unknown_status`, `unknown_expense`, `expense_not_linked`,
`unknown_action`, `invalid_field_null`, `period_invalid`, `reimbursement_empty`,
`approved_amount_invalid`, `decision_reason_required`.
**409**: `REIMBURSEMENT_TRANSITION_INVALID`, `REIMBURSEMENT_EXPENSE_LINKED`.
**404**: `REIMBURSEMENT_NOT_FOUND`, `BUDGET_DISABLED`.

### Слой 5 — API `reimbursement_api.py` (9 роутов)

| Метод + путь | Назначение |
|---|---|
| `POST /budget/reimbursements` | создать черновик |
| `GET /budget/reimbursements` | список (`?status=`, пагинация), ETag/304 |
| `GET /budget/reimbursements/{id}` | деталь + состав |
| `PATCH /budget/reimbursements/{id}` | правка реквизитов (статус не трогает) |
| `DELETE /budget/reimbursements/{id}` | soft-delete черновика |
| `POST /budget/reimbursements/{id}/items` | привязать расход |
| `DELETE /budget/reimbursements/{id}/items/{expense_id}` | отвязать |
| `POST /budget/reimbursements/{id}/{action}` | FSM: `submit\|approve\|reject\|pay` |

- **Порядок объявления критичен:** `/items` и `/items/{expense_id}` идут **до** `/{id}/{action}`,
  иначе `POST .../items` ушёл бы в FSM с `action="items"`. Запинено тестом.
- RBAC: `admin` / `owner` / `accountant` / `ot_pb_lead`, единый ABAC на чтение и запись.
- Feature-флаг `budget`, default-off → 404 `BUDGET_DISABLED` на всех роутах.
- **ETag списка включает скаляр состава** (`id:count:amount` по строкам). Без него привязка расхода
  не меняла бы `(id, updated_at)` заявки и список отдавал бы 304 с устаревшим составом.
- Схемы: `ReimbursementCreate` не принимает `status`; `ReimbursementUpdate` не принимает
  `status`/`approved_amount`/`decision_reason` — они меняются только через FSM-действия.
- Аудит пишется **до** `session.commit()`, в одной транзакции с мутацией.

### Слой 6 — фронт

Вкладка «Возмещения СФР» на `/budget` (`features/budget/ReimbursementsTab.tsx`) + диалог формы.
`ACTIONS_BY_STATUS` — зеркало серверного FSM; «Изменить»/«Удалить» рендерятся только для `draft`.
Клиентские проверки (сумма выше запрошенной, пустая причина отказа) **дублируют** серверные 422 —
это UX-слой, а не замена валидации. Фильтр по статусу делает собственный запрос с seq-guard от
гонок. Привязка расхода предлагает только ещё не связанные расходы.

### Демо-данные

`_seed_budget_reimbursements_demo()` (`demo_bootstrap.py:1190`) — 3 заявки в состояниях
draft / submitted / approved + 5 строк состава из уже сидируемых расходов. Идемпотентность —
per-claim `SELECT` по натуральному ключу `(tenant_id, title, deleted_at IS NULL)`, тот же ключ,
что у демо-расходов.

## Верификация

- **Backend по фиче — 37 тестов:** `test_budget_reimbursement_api.py` (13 HTTP: флаг, RBAC,
  CRUD+состав, FSM, 409-конфликты, матрица 422, ETag/304 с инвалидацией при привязке, порядок
  роутов), `test_budget_reimbursement_service.py` (20), `test_budget_reimbursement_lifecycle.py` (4).
- **Frontend — 8 тестов вкладки** в `BudgetPage.test.tsx`.
- **Полные прогоны (весь бэкенд / весь фронт) на этой ветке НЕ гонялись** — см. handoff-блок
  `AI_IMPLEMENTATION_REPORT.md`. Зелёные только целевые выборки по фиче, `typecheck`, `vite build`,
  `ruff --no-fix`, `check_openapi_snapshot.py`.
- OpenAPI baseline: **888 операций / 751 схема** (+8 операций, только добавления).

## Осознанно отложено (срез-3+)

- Печатная форма заявки и пакет документов в СФР.
- Автоподбор расходов в заявку по периоду и домену (сейчас — ручная привязка).
- Вход СИЗ-закупок в состав заявки (нужна связка склад→расход, наследие среза-1).
- Частичная выплата и график платежей (сейчас `paid` — единичный терминальный факт).
- Экспорт заявок в report-builder; мультивалюта.
