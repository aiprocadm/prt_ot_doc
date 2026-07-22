# SEC-65 — RLS как второй рубеж изоляции арендаторов (пилот на комитетах) — design spec

- **Дата:** 2026-07-22
- **Статус:** approved (пилотный набор таблиц + строгость зафиксированы пользователем через AskUserQuestion)
- **Ветка:** `feat/sec65-rls-committees-pilot` от `main` (head после мержа PR #774 SSRF).
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B-NEXT.7 → «RLS как второй рубеж изоляции — разд. 65». Матрица: `TZ_COVERAGE_MATRIX.md` SEC-65 (`missing` → `partial(committees_pilot)`). Roadmap Phase 16: «RLS — additive expand-contract миграция, применять **только по подтверждённому плану и списку таблиц**».
- **Только PostgreSQL.** RLS в SQLite нет — миграция и обвязка на SQLite **no-op** (основной тест-набор на SQLite не затрагивается). Реальная проверка изоляции — в `-m db` тестах (Postgres).

## 1. Контекст (сверка код↔ТЗ)

Изоляция арендаторов сейчас — **прикладная**: фильтр `WHERE tenant_id = …` в коде + `db/tenant_row_guard.py` (before_flush сравнивает `row.tenant_id` с сессией). Если запрос забудет фильтр — утечёт чужое. RLS вшивает правило в саму БД: второй замок, не зависящий от корректности прикладного кода.

Многотенантность — **общая схема** (`public`), каждая таблица с колонкой `tenant_id` (опц. per-tenant `search_path`-схема). Значит политика вида `tenant_id = current_setting('app.current_tenant')` ложится напрямую.

**Точка обвязки найдена:** `db/session.py::TenantAsyncSession.__aenter__` (стр. 38) уже вызывает `_apply_search_path`, который на Postgres (`_SUPPORTS_SCHEMAS = dialect=='postgresql'`) делает `SET LOCAL search_path`/`application_name`. Сюда же — установка RLS-GUC. `session.info["tenant_id"]` — источник текущего арендатора.

## 2. Решения (зафиксированы пользователем через AskUserQuestion)

1. **Пилотный набор = семейство комитетов, 8 таблиц** (все с `tenant_id`, наследуют `TenantBaseModel`): `committee`, `committee_member`, `committee_meeting`, `committee_agenda_item`, `committee_decision`, `committee_decision_task`, `committee_meeting_attendance`, `committee_decision_vote`. Знакомый домен (срез-1..3), низкий риск, есть демо-данные для живой проверки. Остальные ~200 таблиц — следующими срезами по этому же образцу.
2. **Строго: FORCE ROW LEVEL SECURITY + bypass-GUC.** Правило действует даже если приложение ходит в БД владельцем таблиц (иначе RLS — no-op). Системные/фоновые кросс-тенант операции ставят явный bypass-флаг.

## 3. Не-цели (осознанно вне объёма)

- RLS на остальных ~200 таблицах (следующие срезы по образцу пилота).
- Отдельная БД-роль для приложения (сейчас переиспользуем bypass-GUC; смена роли — инфра-решение вне кода).
- Автопроверка «на всех tenant-таблицах включён RLS» в CI (можно добавить срезом позже — линтер по `information_schema`).
- Перевод прикладного `tenant_row_guard` в off (остаётся первым рубежом — defense-in-depth).

## 4. Механизм (без изменения данных; DDL-миграция аддитивна)

**GUC (сессионные переменные, transaction-local):**
- `app.current_tenant` — id текущего арендатора; ставится из `session.info["tenant_id"]`.
- `app.bypass_rls` — `'on'` для доверенных системных сессий (сид/фон/кросс-тенант).

**Политика на каждой из 8 таблиц** (`FOR ALL`, одинаковый USING и WITH CHECK):
```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t> FOR ALL
  USING      (current_setting('app.bypass_rls', true) = 'on'
              OR tenant_id = current_setting('app.current_tenant', true))
  WITH CHECK (current_setting('app.bypass_rls', true) = 'on'
              OR tenant_id = current_setting('app.current_tenant', true));
```
`current_setting(name, true)` — `missing_ok`, вернёт NULL если GUC не задан. Нет тенанта и нет bypass → `tenant_id = NULL` → **deny (fail-closed)**. Это и есть «второй рубеж»: забыли контекст → база молчит, а не отдаёт всё.

## 5. Backend — обвязка сессии (`db/session.py`)

- Новая `async def _apply_tenant_rls(session)` — на `_SUPPORTS_SCHEMAS` (Postgres) исполняет `SELECT set_config('app.current_tenant', :tid, true)` (параметр-безопасно; `true` = local), либо при `session.info["rls_bypass"]` → `set_config('app.bypass_rls','on',true)`. На SQLite — ранний `return` (no-op).
- Вызов в `TenantAsyncSession.__aenter__` **сразу после** `_apply_search_path`.
- `AsyncSessionLocal(..., rls_bypass=False)` + `session_scope(..., rls_bypass=False)` — новый параметр, пишет `session.info["rls_bypass"]`. Дефолт False.
- **Демо-сид** `demo_bootstrap.py::bootstrap_demo_tenant` открывает `session_scope(tenant="public")` — кросс-тенант системный сид → передать `rls_bypass=True` (иначе FORCE RLS заблокирует INSERT в `committee*`). Прочие сидеры/фоновые пути, пишущие в комитеты **без** тенант-контекста, — тоже `rls_bypass=True` (для пилота проверяется тестами и живым сидом).

## 6. Миграция

`backend/app/migrations/versions/20260722_sec65_rls_committees.py`, `down_revision = "20260719_bg02_budget_reimbursement"` (текущая head). **Гард: `if op.get_bind().dialect.name != "postgresql": return`** — на SQLite ничего не делает. upgrade — ENABLE+FORCE+POLICY на 8 таблиц; downgrade — DROP POLICY + DISABLE (в обратном порядке). Идемпотентность не требуется (alembic ведёт версию), но имена политик фиксированы (`tenant_isolation`).

## 7. Frontend / demo-seed

Фронта нет. Демо-сид данные не меняет (только флаг `rls_bypass=True` на его сессии).

## 8. Тест-план

**`-m db` (Postgres, реальная проверка — SQLite RLS не поддерживает):** `backend/tests/test_rls_committees.py` (НОВЫЙ, маркер `db`):
- Два арендатора A и B, по комитету у каждого (INSERT под `rls_bypass` или под своим тенант-контекстом).
- Сессия с `app.current_tenant=A` (обычная tenant-сессия) видит **только** комитеты A; строки B невидимы (SELECT count = 1).
- INSERT комитета с `tenant_id=B` из сессии A → **заблокирован** (WITH CHECK violation).
- Сессия без тенанта и без bypass → видит **0 строк** (fail-closed).
- Сессия с `rls_bypass=True` → видит комитеты обоих (bypass работает).
- FORCE проверяется тем, что тесты идут под owner-подключением (testuser=суперюзер) и всё равно фильтруются.

**Регресс на SQLite (основной набор):** миграция и обвязка — no-op; committees/api/demo-bootstrap тесты остаются зелёными (проверить `test_committees_*`, `test_demo_bootstrap_*`).

**Существующие `-m db` тесты** (`test_alembic_postgres_upgrade`, `test_orm_enum_pg_label_parity`): моя миграция должна применяться/откатываться чисто; enum-parity не пишет в `committee*` без контекста — проверить, что зелёные.

**Гейты:**
1. `-m db` (Postgres) — новые RLS-тесты + существующие 5 (upgrade/downgrade/enum) зелёные.
2. Полный бэкенд-suite на SQLite (`-n 6 --timeout 600`) — без регресса.
3. `ruff --no-fix` + format.
4. OpenAPI snapshot — не меняется (роутов нет).
5. `TZ_COVERAGE_MATRIX.md` SEC-65 → `partial(committees_pilot)`; handoff + CHANGELOG.

## 9. Риски / грабли

- **FORCE ломает системные вставки без тенант-контекста** → bypass-GUC + `rls_bypass=True` на демо-сиде (и на любых кросс-тенант сидерах/джобах, пишущих в комитеты). Ловится живым сидом + db-тестом «bypass видит всё».
- **SQLite не знает RLS** → миграция и обвязка гардятся `_SUPPORTS_SCHEMAS`/`dialect=='postgresql'`; основной набор не затрагивается.
- **transaction-local GUC**: `set_config(...,true)` живёт в пределах транзакции; при пуле соединений утечки нет (сбрасывается на commit/rollback). Ставится в `__aenter__` внутри активной транзакции (как `SET LOCAL search_path` рядом).
- **fail-closed** может неожиданно спрятать данные, если какой-то путь пишет/читает комитеты без тенант-контекста и без bypass → пилот на 8 таблицах это выявит на тестах/сиде до расширения на остальные.
- **Downgrade-симметрия** (как учил недавний баг iter26): upgrade и downgrade строго зеркальны, проверяется `test_alembic_downgrade_base_then_reupgrade`.

## 10. Порядок реализации

1. Обвязка `db/session.py` (`_apply_tenant_rls` + `rls_bypass` в `AsyncSessionLocal`/`session_scope`) + `rls_bypass=True` в демо-сиде.
2. Миграция (Postgres-only, 8 таблиц).
3. `-m db` тесты RLS.
4. Гейты: db-тесты (Postgres), полный SQLite-suite, ruff, openapi; матрица + handoff + CHANGELOG.
