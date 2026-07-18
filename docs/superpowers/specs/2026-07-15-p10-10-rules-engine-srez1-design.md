# P10-10 Rules-engine срез-1 — дизайн (2026-07-15)

Канон требований: ТЗ B.24 → vNext §25.2 («условия / действия / приоритеты / dry-run / тестирование правил / лог срабатываний / версии / tenant overrides»).

**Объём среза-1 (решение пользователя):** ядро — CRUD правил (условия + действия + приоритет + вкл/выкл), срабатывание на доменных событиях, лог срабатываний, dry-run + тестирование по истории, admin-UI на новой странице `/rules`. **Версии правил и tenant overrides — срез-2.**

**Решения (AskUserQuestion, 2026-07-15):**
1. Срез = P10-10 rules-engine (из кандидатов: P10-01 срез-3, §12.4 бюджет, contractors follow-ups).
2. Объём = ядро без версий/overrides (см. выше).
3. Действия = создать задачу + in-app уведомление + webhook.
4. UI = новая страница `/rules` (паттерн ReportBuilderPage), не визуальный редактор.
5. Точка срабатывания = **синхронный hook в `OutboxService.enqueue`** (та же транзакция, что и доменное событие).

## 0. Контекст интеграции (разведка 2026-07-15, main@7cacee45)

- Все доменные события идут через `OutboxService.enqueue` (`backend/app/services/outbox.py:127`) — 26 точек вызова; payload нормализуется по typed-моделям `backend/app/services/events.py` (`EventType`, `_PAYLOADS`, `dedupe_key_for`). `payload["correlation_id"]` авто-заполняется, `event_id` бэкфиллится id outbox-строки.
- **Outbox-доставку никто не запускает по умолчанию**: `outbox.dispatch` (`backend/app/tasks/_core.py:114`) не в `beat_schedule` (`backend/app/services/celery_app.py:50-87`); dev-lite (`scripts/dev_lite.py`) — без worker/beat, `CELERY_EAGER=true`. Поэтому async-consumer нежизнеспособен; sync-hook — единственный работающий везде вариант.
- Прото-механизмы, которые срез обобщает (НЕ трогаем, работают параллельно):
  - `ReminderRule` (`backend/app/models/notifications.py:171`) + `reminders.scan` — дедлайн-напоминания по расписанию;
  - жёсткий мост outbox→уведомление на 6 типов событий только для `actor_id` (`backend/app/tasks/_core.py:345-377`).
- Условия в workflow-движке (`WorkflowService._condition_matches`, `modules/workflow/service.py:676`) — микро-DSL рёбер (`==`/`!=`/truthiness), не переиспользуем и не ломаем.
- Действия — готовые механизмы:
  - Задачи: `Task` (`backend/app/models/obligations.py:39`, таблица `task`); прецеденты создания — `backend/app/services/obligations.py` (flush-only, caller owns commit; `next_task_reminder` для `next_remind_at`); у Task нет колонки происхождения — используем `entity_type="automation_rule"`, `entity_id=rule_id`.
  - Уведомления: `send_notification` (`backend/app/services/notifications.py:57`) — flush-only, возвращает `None` при opt-out, существующую строку при dedup-хите; `dedup_key` **глобально** уникален → обязан содержать tenant-зависимую часть; резолв получателей по ролям — по образцу `_resolve_rule_recipients` (`backend/app/tasks/notification_jobs.py:101`), `User.role` — единственная роль (enum).
  - Webhook: enqueue нового typed-события через существующий конвейер (destination-резолв по webhook-подпискам tenant'а).
- Feature-флаги: `is_feature_enabled(..., default=False)` (`backend/app/core/feature_flags.py:22`); гейт-стиль report_builder — `FeatureGate = Depends(_require_feature)` → 404 `api_problem_detail(code="RULES_ENGINE_DISABLED")` (`backend/app/modules/report_builder/api.py:63-99`). `Feature` — SharedModel, `FeatureEnablement` — TenantBaseModel, между ними НЕТ FK (разные metadata).
- RBAC: только `abac(_tenant_resource_id, required_roles=[...], action=...)`; router-level guard — паттерн analytics (`backend/app/modules/analytics/api.py:41-52`). Маршрут без abac/rbac достижим неаутентифицированно (инвариант auth-enforcement).
- Demo-сид: `backend/app/services/demo_bootstrap.py` (`bootstrap_demo_tenant`, идиома Feature/FeatureEnablement/natural-key — строки 799-847), НЕ `dev_bootstrap.py`.
- Регистрация роутера: `backend/app/api/v1/route_groups.py` (кортежи `*_ROUTER_REGISTRATIONS`); новые операции меняют OpenAPI-снапшот → пере-снять baseline в том же PR.
- Frontend-паттерны: typed api-модуль поверх `apiClient` (`frontend/src/api/client.ts:156`); `isFeatureDisabledError` — модульная копия (прецедент `api/contractors.ts:31`, regex `/feature is not enabled/i` — наш 404-detail должен матчиться, см. §4); `useAsyncResource` (loader в `useCallback`!); 4 точки проводки страницы + feature-флаг в `router/navVisibility.ts:14-16`; dry-run — POST (GET авто-ретраится клиентом при 5xx); ближайший прецедент UI — `pages/reports/ReportBuilderPage.tsx` (FilterRow-конструктор, discriminated-union состояний).

## 1. Данные — миграция `re01` (аддитивная, от текущего head)

### `automation_rule` (TenantBaseModel + SoftDeleteMixin)
| Поле | Тип | Примечание |
|---|---|---|
| `name` | String(255) NOT NULL | уникальность per tenant **без** deleted_at-фильтра (паттерн `report_definition`; пин-тест с soft-deleted тёзкой) |
| `description` | Text NULL | |
| `event_type` | String(64) NOT NULL | значение `EventType.value`; валидируется на API; индекс `(tenant_id, event_type)` |
| `conditions_json` | JSONB/JSON NOT NULL default `{}` | см. формат ниже |
| `actions_json` | JSONB/JSON NOT NULL default `[]` | список действий, ≤10 |
| `priority` | Integer NOT NULL default 100 | меньше = раньше; порядок оценки `(priority, created_at)` |
| `is_enabled` | Boolean NOT NULL default true | |

Формат условий:
```json
{"match": "all" | "any",
 "conditions": [{"field": "severity", "op": "in", "value": ["high", "critical"]}]}
```
- `field` — dot-путь по нормализованному payload (`"before.level"` допустим);
- `op` ∈ `eq, ne, in, not_in, gt, gte, lt, lte, contains, exists`;
- пустой `conditions` = правило матчит любое событие своего `event_type`;
- ≤20 условий; `value` для `in/not_in` — список ≤50 элементов.

### `automation_rule_trigger` (TenantBaseModel, append-only лог)
| Поле | Тип | Примечание |
|---|---|---|
| `rule_id` | FK `automation_rule.id` CASCADE, indexed | |
| `event_type` | String(64) NOT NULL | |
| `event_key` | String(255) NOT NULL | idempotency-ключ исходного события (или `event_id`) |
| `correlation_id` | String(128) NULL | из payload |
| `event_payload` | JSONB/JSON NOT NULL | снапшот на момент срабатывания |
| `status` | native enum `ruletriggerstatus`: `success / partial / error` | в миграции — `postgresql.ENUM` (правило rel1-гейта) |
| `actions_result` | JSONB/JSON NOT NULL default `[]` | per-action: `{"type", "outcome": "created/deduped/suppressed/error", "detail?", "entity_id?"}` |

Индексы: `(tenant_id, rule_id, created_at)`, `(tenant_id, created_at)`. Лог пишется **только при совпадении условий** (или при ошибке оценки/действий); dry-run и test лог НЕ пишут.

## 2. Движок — `backend/app/modules/rules_engine/`

```
models.py      # AutomationRule, AutomationRuleTrigger, RuleTriggerStatus
conditions.py  # чистый evaluator: evaluate(conditions_json, payload) -> bool; validate_conditions()
actions.py     # execute_action(session, ctx, action_cfg) -> ActionOutcome; validate_actions()
catalog.py     # интроспекция events._PAYLOADS -> [{event_type, fields: [{name, type}]}]
engine.py      # evaluate_event(session, tenant_id, event_type, payload) — оркестрация
schemas.py     # Pydantic DTO
service.py     # CRUD + dry-run + test
api.py         # router
```

### Hook (единственное изменение вне модуля)
В `OutboxService.enqueue`, **после** успешного создания хотя бы одной **новой** outbox-строки (dedup-реплей → существующая строка → hook НЕ вызывается — ежедневные реплеи тиков не перезапускают правила):

```python
# outbox.py, конец enqueue()
if any_new_row and resolved.value != RULE_TRIGGERED_EVENT:
    await _evaluate_automation_rules(...)   # lazy import modules.rules_engine.engine
```

Внутри `evaluate_event`:
1. feature-флаг `rules_engine` (`is_feature_enabled(..., default=False)`) — выключен → return;
2. SELECT включённых правил `(tenant_id, event_type, is_enabled=true, deleted_at is null)` order by `(priority, created_at)`;
3. для каждого правила: `conditions.evaluate` → при матче — исполнить действия по порядку, собрать `actions_result`, записать строку лога;
4. **весь** вызов hook'а обёрнут `try/except Exception` → `logger.exception` + best-effort строка лога `status=error`; исходная транзакция события НЕ страдает ни при каком сбое движка.

Guard от рекурсии: события `rule.triggered` не оцениваются (глубина каскада = 1). Никакого кеша правил в срезе-1 — один индексированный SELECT на эмиссию события при включённом флаге.

### Действия (все flush-only, транзакция общая с событием)
1. **`create_task`** — конфиг `{type: "create_task", title_template, description_template?, assignee_mode: "none"|"actor"|"user_id", user_id?, due_in_days?, priority: "low"|"medium"|"high"|"critical"}`. Создаёт `Task` с `entity_type="automation_rule"`, `entity_id=rule_id`, `created_by=actor_id?`, `next_remind_at` через `next_task_reminder`. Дедуп: перед созданием — SELECT в trigger-логе по `(tenant_id, rule_id, event_key)`; если строка уже есть (реплей в новой транзакции) → outcome `deduped`.
2. **`notify`** — конфиг `{type: "notify", recipient_mode: "actor"|"user_id"|"role", user_id?, roles?: [...], title_template, body_template, priority?}`. Канал среза-1 — только INAPP. Резолв получателей: `actor` → `payload.actor_id` (нет → `suppressed`); `role` → SELECT User по ролям tenant'а (свой резолвер в actions.py по образцу `_resolve_rule_recipients`). `dedup_key = f"rules:{rule_id}:{event_key}:{user_id}"` (`event_key` содержит tenant-зависимую часть; глобальная уникальность dedup-индекса соблюдена). Исходы: `created` / `deduped` (вернулась существующая строка) / `suppressed` (opt-out → None).
3. **`webhook`** — конфиг `{type: "webhook"}` (без параметров в срезе-1). Enqueue нового typed-события `RULE_TRIGGERED = "rule.triggered"` c payload `{rule_id, rule_name, source_event_type, source_event_id?, source_payload}` → доставка webhook-подпискам tenant'а существующим конвейером. Регистрация: `EventType.RULE_TRIGGERED`, `RuleTriggeredPayload(BaseEventPayload)` в `_PAYLOADS`, ветка в `dedupe_key_for` (`f"rule-triggered:{rule_id}:{source_event_key}"`).

Сбой одного действия → outcome `error` в `actions_result`, остальные действия исполняются; статус строки лога: все ok → `success`, часть ошибок → `partial`, ошибка оценки/всё упало → `error`.

### Шаблоны строк
`{field}`-подстановка значений payload по dot-пути (регэксп `\{[a-zA-Z0-9_.]+\}`, без eval/format-spec; отсутствующее поле → пустая строка; не-строковые значения → `str()`). Лимит длины результата — 255 для title, 2000 для body.

## 3. API — `/rules/*`, флаг + ABAC router-level

- Роутер: `APIRouter(prefix="/rules", tags=["rules-engine"], dependencies=[_Guard, FeatureGate])`, где `_Guard = Depends(abac(_tenant_resource_id, required_roles=["admin", "owner"], action="manage automation rules"))`, `FeatureGate` — 404 `api_problem_detail(code="RULES_ENGINE_DISABLED", error_type="rules_engine")`, detail-текст содержит «feature is not enabled» (совместимость с фронтовым `isFeatureDisabledError`).
- Эндпоинты:
  - `GET /rules/event-types` — каталог: `[{event_type, fields: [{name, type}]}]` из `catalog.py` (RU-лейблы — только во фронтовом vocab);
  - `GET /rules` — список `{items, total, limit, offset}` + ETag/304 (паттерн report_builder);
  - `POST /rules` — 201; 409 `RULE_NAME_EXISTS` (дубль имени), 422 typed-коды валидации (`unknown_event_type`, `invalid_condition_field/op/value`, `invalid_action`, лимиты);
  - `GET /rules/{id}` · `PATCH /rules/{id}` (частичное обновление; та же валидация) · `DELETE /rules/{id}` — 204 soft-delete;
  - `POST /rules/dry-run` — body `{rule: RuleConfigInline, event: {event_type, payload}}` → `{matched: bool, condition_results: [{field, op, value, actual, matched}], would_actions: [{type, summary}]}`; ничего не пишет;
  - `POST /rules/{id}/test` — body `{limit?: int<=50}` → прогон по последним N историческим событиям типа правила из outbox-строк (`SELECT DISTINCT ON idempotency_key ... ORDER BY created_at DESC`; SQLite-совместимо — группировка в Python) → `{events_checked, matched_count, results: [{event_key, occurred_at?, matched}]}`; ничего не исполняет и не пишет;
  - `GET /rules/triggers?rule_id=&limit=&offset=` — журнал срабатываний, сортировка `created_at desc`.
- Audit (`AuditService.log_event`) на create/update/delete.
- Регистрация в `route_groups.py`; **OpenAPI baseline пере-снять в том же PR** (ARCH-4).

## 4. Frontend — страница `/rules` («Правила автоматизации»)

- Права: `RULES_VIEW = "rules.view"`, `RULES_MANAGE = "rules.manage"` в `permissions/permissions.ts`; в `ROLE_PERMISSIONS` НЕ добавляем ни одной роли явно — owner/admin получают через ALL_PERMISSIONS (backend-гейт admin/owner; консистентно).
- Проводка: `pageRegistry.tsx` (lazy `RulesPage`), `routeGroups.tsx` (группа под `RULES_VIEW`), `navigationConfig.ts` (пункт «Правила автоматизации» в администрирование/настройки-группу), `navVisibility.ts` (скрыть при `featureFlags.rules_engine === false`).
- `api/rules.ts` — typed-модуль (методы: eventTypes, list, create, get, update, remove, dryRun, test, triggers) + модульный `isFeatureDisabledError` + DTO в `types/dto/rules.ts`.
- `pages/rules/RulesPage.tsx` + `rulesVocab.ts` (RU-лейблы событий/операторов/действий/статусов/исходов):
  - Реестр правил: RegistryTable (имя, событие, действия-бейджи, приоритет, вкл/выкл Switch → PATCH, срабатываний за период — нет, просто последнее срабатывание не тянем в срезе-1);
  - `RuleFormDialog` (Radix Dialog + DialogDescription): селект события (из каталога) → строки условий (field-селект из каталога полей / op-селект / value-инпут, типо-зависимый) → конструктор действий (карточки по типам с конфигом) → приоритет; create/edit;
  - Панель **Dry-run**: селект события → textarea JSON-payload (плейсхолдер-пример из каталога полей) → POST dry-run → разбор per-условие + список would-actions;
  - Кнопка **«Тест по истории»** на правиле → POST test → диалог с match-rate и таблицей событий;
  - Панель **«Журнал срабатываний»**: фильтр по правилу, таблица (время, правило, событие, статус, actions_result-бейджи), `useAsyncResource`.
- Feature-off → `EmptyState «Функция недоступна»` (через `isFeatureDisabledError`); ошибки — `ErrorState`, без дублирующих toast'ов на 4xx.

## 5. Ошибки / безопасность / идемпотентность

- Изоляция hook'а: никакой сбой движка не роняет исходную транзакцию; ошибки — в лог (`status=error`) + `logger.exception`.
- Идемпотентность: (а) оценка только новых outbox-строк; (б) дедуп `create_task` по trigger-логу `(rule_id, event_key)`; (в) `notify` дедупится нативным `dedup_key`; (г) `webhook` — outbox `idempotency_key`.
- Tenant-изоляция: `tenant_id` — из аргумента `enqueue` (который берётся из AccessContext вызывающих сервисов); правила/лог — TenantBaseModel; никаких X-Tenant-Id.
- Валидация на API: whitelist событий (из `EventType`), полей (из каталога; неизвестное поле в условии — 422), операторов, типов действий; лимиты ≤20 условий / ≤10 действий / ≤50 элементов `in`.
- Оценка условий устойчива к отсутствующим полям (`exists=false`, сравнения с None → не матч, не исключение); сравнение чисел — приведение через Decimal/float с фолбэком «не матч».

## 6. Тестирование, сид, гейты

- **Unit**: `conditions.py` — таблица кейсов (каждый op × наличие/отсутствие поля × dot-путь × типы значений); `actions.py` — исходы created/deduped/suppressed/error; шаблоны; `engine.py` — приоритет-порядок, loop-guard (`rule.triggered`), изоляция ошибок, флаг-off.
- **API-контракт**: CRUD (+409 дубль, 422 коды, 404 flag-off, 401/403 RBAC-границы — с auditor_ro/ot_specialist негатив), dry-run (matched/не-matched, разбор условий), test-by-history, журнал.
- **Интеграция**: включить флаг → enqueue `IncidentCreated(severity=critical)` через `OutboxService` → проверить Task (entity_type=automation_rule) + Notification (dedup_key) + строку лога; реплей с тем же idempotency_key → без новых действий; правило на `rule.triggered` создать нельзя (422) и события каскада не оцениваются.
- **Пин-тесты**: уникальность имени с soft-deleted тёзкой; RBAC-граница (владельцы читают/пишут, остальные 403); webhook-действие рождает outbox-строку `rule.triggered` с корректным dedupe-ключом.
- **Demo-сид** (`demo_bootstrap.py`): `Feature(rules_engine)` + `FeatureEnablement(on=True)` + 2 правила: «Критичный инцидент → задача + уведомление админам» (`IncidentCreated`, `severity in [high, critical]`, create_task+notify role=admin), «Истечение документа подрядчика → уведомление админам» (`contractor.document_expiring`, notify role=admin). Идемпотентно по natural-key `name`.
- **Гейты перед PR**: ruff+black; backend pytest (батчи ≤5, PowerShell, timeout 600000, `-p magic_stub` при зависании импорта); PG16 `scripts/ci/local_gate.py --db-only` (миграция `re01` + native enum round-trip); OpenAPI baseline reген + `✓ ARCH-4`; фронт `tsc --noEmit` / vitest / `vite build`.

## 7. Осознанно отложено (срез-2+)

- Версии правил (draft/published, лог → version_id) и tenant overrides / системный каталог правил.
- Действие «запустить workflow-инстанс»; email/telegram-каналы в `notify`; параметризованный webhook (свой URL в конфиге действия).
- Cron-условия/расписания (остаётся у `ReminderRule`); объединение с `ReminderRule` и мостом `_core.py:345` (после стабилизации движка — кандидат на миграцию на правила).
- Счётчики срабатываний на реестре, retention/очистка лога, кеш правил в hook'е, rate-limit действий.
- Smart Recommendations (§25.3) — отдельный под-проект (проекции, не событийные правила).
