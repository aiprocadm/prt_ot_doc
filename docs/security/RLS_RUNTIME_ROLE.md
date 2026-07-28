# SEC-65: роль БД, к которой RLS реально применяется

Раскатанные политики Row Level Security (264 из 265 tenant-таблиц) защищают данные
**только если приложение ходит в базу непривилегированной ролью**. PostgreSQL
пропускает проверку row security для ролей с атрибутом `SUPERUSER` или `BYPASSRLS`,
и `FORCE ROW LEVEL SECURITY` на таблице этого не меняет. До этой правки эталонный
`docker-compose.yml` подключался ролью-бутстрапом кластера (`POSTGRES_USER`), то
есть все политики были декоративными.

Разделение ролей:

| Переменная | Роль | Кто использует | Зачем |
|---|---|---|---|
| `MIGRATION_DATABASE_URL` | владелец (`ptd`) | только Alembic | `ENABLE`/`FORCE ROW LEVEL SECURITY` — DDL, доступный лишь владельцу таблицы |
| `DATABASE_URL` | приложение (`ptd_app`) | API, Celery worker/beat | обычный DML; политики к ней применяются |

Если `MIGRATION_DATABASE_URL` не задана, Alembic берёт `DATABASE_URL` — это
допустимо для SQLite и одно-ролевых стендов.

## Новый кластер (docker compose)

Задайте в `.env`:

```
APP_DB_USER=ptd_app
APP_DB_PASSWORD=<сильный пароль>
DATABASE_URL=postgresql+asyncpg://ptd_app:<пароль>@postgres:5432/ptd
MIGRATION_DATABASE_URL=postgresql+asyncpg://ptd:<пароль владельца>@postgres:5432/ptd
```

`infra/postgres/initdb/10-app-role.sh` создаст роль при первой инициализации
кластера. Хук выполняется **только на пустом каталоге данных** — на уже
существующем томе он не сработает, используйте следующий раздел.

## Существующий кластер

```bash
PYTHONPATH=backend python scripts/provision_app_role.py \
    --admin-url postgresql://ptd:<пароль>@localhost:5432/ptd \
    --role ptd_app --password "$APP_DB_PASSWORD"
```

Скрипт идемпотентен: создаёт или чинит роль, выдаёт гранты на `public` и все
существующие схемы `tenant_*`, и прописывает `ALTER DEFAULT PRIVILEGES`, чтобы
таблицы будущих миграций были доступны автоматически. **Запускайте его после
миграций, которые создают новые схемы `tenant_*`** — дефолтные привилегии
действуют внутри схемы, а не поверх всей БД.

После этого переключите `DATABASE_URL` на новую роль и перезапустите API и Celery.

## Проверка

```bash
# 1. Сторож (то же самое гоняет CI)
PYTHONPATH=backend python scripts/ci/check_rls_runtime_role.py

# 2. Вручную, тем же соединением, что и приложение
psql "$DATABASE_URL" -c "SELECT current_user, rolsuper, rolbypassrls
                         FROM pg_roles WHERE rolname = current_user"

# 3. Семантика политик на настоящих таблицах (нужен живой PostgreSQL)
PYTHONPATH=backend TEST_PG_ADMIN_URL="postgresql://<superuser>@localhost:5432/postgres" \
    python -m pytest backend/tests/test_rls_runtime_role_db.py \
                     backend/tests/test_rls_auth_queues_final.py -q -p no:randomly
```

Ожидаемо: `rolsuper = f`, `rolbypassrls = f`.

## Поведение при неправильной роли

* `APP_ENV=production` или `staging` — API и Celery worker **не стартуют**:
  `UnsafeDatabaseRoleError`, в логе `app.startup.unsafe-db-role` /
  `celery.startup.unsafe-db-role`.
* `development` / `test` — старт продолжается, в лог пишется
  `rls.runtime_role.unsafe`. Локальная разработка на бутстрап-суперюзере остаётся
  рабочей.
* Переопределение в обе стороны: `RLS_REQUIRE_UNPRIVILEGED_DB_ROLE=true|false`.

## Предполётная проверка перед понижением роли

Сторож покрытия `check_rls_coverage.py` строит список tenant-таблиц из
**метаданных SQLAlchemy**, поэтому не видит две вещи: таблицы с колонкой
`tenant_id`, но без ORM-модели, и копии таблиц в схемах `tenant_<slug>`
(миграции `sec65_rls_*` армируют только `public`). Обе слепые зоны закрывает
аудит по живой базе — **обязательно прогоните его на проде перед переключением
`DATABASE_URL` на непривилегированную роль**:

```bash
PYTHONPATH=backend python scripts/audit/check_rls_live_schema.py
```

Он читает `pg_attribute` и падает, если найдёт неармированную tenant-таблицу.
Именно так были найдены 8 таблиц-дубликатов без моделей (`companies`, `sites`,
`departments`, `persons`, `positions`, `workplaces`, `training_plans`,
`training_plan_items`) — их армирует миграция
`20260728_sec65_rls_model_less_tables`. Такие таблицы перечислены в
`RLS_MODEL_LESS_TABLES` (`backend/app/core/rls_policy.py`).

## Фоновая разгрузка outbox

Обе задачи-диспетчера очереди tenant-скоупные: предиката `tenant_id` в запросах
нет, отбор делает контекст сессии и политики RLS. Фанаут по всем активным
арендаторам — задача `outbox.dispatch_all`.

Расписание **по умолчанию выключено** (`OUTBOX_DISPATCH_SCHEDULE_ENABLED=false`):
раньше разгрузку не запускал никто, поэтому в существующем деплое может лежать
накопленный backlog, и первый же тик отправил бы его подписчикам целиком.
Включайте осознанно, предварительно посмотрев количество необработанных записей:

```sql
SELECT status, count(*) FROM outbox GROUP BY status;
SELECT status, count(*) FROM outbox_events GROUP BY status;
```

Период — `OUTBOX_DISPATCH_SCHEDULE_MINUTES` (по умолчанию 5 минут).

## Частые ошибки

**«Старт упал, а роль вроде непривилегированная».** Проверьте, что приложение
читает именно ту `DATABASE_URL`: pydantic подхватывает `.env` из рабочего каталога
процесса, и он может перекрыть `.env.production` systemd-юнита.

**`permission denied for table ...` после миграции.** Миграция создала таблицу от
владельца, а `ALTER DEFAULT PRIVILEGES` не покрывала эту схему (обычно — новая
`tenant_*`). Перезапустите `scripts/provision_app_role.py`.

**`permission denied to create database/schema`.** Роль приложения получает
`CREATE` на базе, потому что провижининг арендатора создаёт схему `tenant_<slug>`
в рантайме. Это право не даёт читать чужие строки — row security от него не зависит.

**Роль членом привилегированной роли.** Атрибуты `SUPERUSER`/`BYPASSRLS` не
наследуются, поэтому политики применяются, и сторож это пропускает — но пишет
`rls.runtime_role.escalation_possible`: такая роль может добраться до атрибутов
через явный `SET ROLE`. Для продовой роли членство лучше убрать.

См. также: `backend/app/core/rls_policy.py` (реестр таблиц),
`scripts/audit/check_rls_coverage.py` (ратчет-гард покрытия),
`docs/audit/TZ_COVERAGE_MATRIX.md` (строка SEC-65).
