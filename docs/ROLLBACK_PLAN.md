# ROLLBACK PLAN

## Rollback criteria
- Repeated P0 auth/tenant leakage
- Data corruption in document pipeline
- Unrecoverable queue failures impacting critical flows
- Sustained SLA breach without mitigation

## App rollback
1. Freeze traffic (maintenance mode / ingress switch).
2. Deploy previous stable image tag.
3. Keep readonly mode until smoke is green.

## DB rollback approach
- Prefer forward-fix migrations.
- If mandatory rollback: apply tested downgrade path for last release window only.
- Restore DB snapshot if downgrade unsafe.

## Feature-flag mitigation
- Disable non-critical modules (portal exports, advanced replace, optional webhooks) via flags.
- Keep core tenant/auth/docs flows active.

## Emergency tenant suspension
- Suspend impacted tenant in admin.
- Stop API token issuance for tenant.
- Preserve audit trail and snapshot affected records.

## Queue freeze procedures
- Freeze export/sign/EDO dispatch workers.
- Drain/park pending jobs.
- Resume only after fix verification.

---

## Способ раскатки и SLA отката (OPS-74 разд. 74.1/74.3/74.4)

> Решения приняты 2026-09-14 (делегированы владельцем). До этого строка OPS-74
> держала в остатке «rolling/blue-green, canary, SLA отката, среды» с пометкой
> «это процесс, а не код». Процессная половина записана здесь; кодовая —
> `backend/app/core/schema_readiness.py` (готовность по схеме) и
> `tests/test_migrations_expand_contract.py` (expand-contract + рабочий откат).

### Стратегия: rolling с health-gate, НЕ blue-green

Выбран **rolling**: экземпляры заменяются по одному, следующий берётся только
после того, как предыдущий ответил «готов».

Почему не blue-green. Blue-green удваивает инфраструктуру приложения, но база у
обеих половин ОДНА — схемы арендаторов живут в одном кластере. То есть главный
риск выката (несовместимая схема) blue-green не снимает, а платить за него
надо вдвойне. Совместимость схемы обеспечивает expand-contract, и она же делает
rolling безопасным.

### Что означает «ответил готов»

`GET /api/v1/health/ready` возвращает 200 только когда живы Postgres, Redis,
хранилище файлов **и совпадает схема**. Правило по схеме несимметрично:

* код впереди базы — **не готов** (мои миграции не накатаны, я знаю про колонки,
  которых нет);
* база впереди кода — **готов** (штатная expand-фаза; старый код обязан работать
  против новой схемы, это стережёт `test_migrations_expand_contract.py`);
* ревизия базы коду неизвестна — **не готов** (откат кода назад при уже
  накатанной базе).

Без этой проверки новый экземпляр рапортовал «готов» сразу после подъёма — база
отвечает на ping задолго до того, как на неё накатили миграции, — и получал
трафик, которого не мог обслужить.

### Канареечный этап

1. Заменить **один** экземпляр (или 10% при числе больше десяти).
2. Держать **15 минут** под наблюдением: доля ответов 5xx, задержка 95-го
   перцентиля, длина очереди задач, ошибки в журнале.
3. Ухудшение любого из четырёх — откат, не разбираясь. Разбираться на откате
   дешевле, чем на трафике.
4. Всё ровно — заменить остальные порциями по четверти.

### SLA отката

| Событие | Срок |
|---|---|
| Решение «откатываем» после срабатывания тревоги | **10 минут** |
| Трафик на прежней версии | **15 минут** от решения |
| Сообщение арендаторам, если простой был заметен | **60 минут** |

Откат приложения — это выкат предыдущего образа: образы предыдущих трёх
релизов хранятся всегда, поэтому откат не требует сборки.

**Откат базы — отдельное решение и почти всегда не нужен.** Правило по
умолчанию: forward-fix. Разрушительная миграция обязана иметь рабочий
`downgrade` (сторож падает, если он пуст) — но применять его допустимо только в
окне текущего релиза и только когда данные заведомо не менялись. Иначе —
восстановление из снимка.

### Среды

| Среда | Что это | Правило |
|---|---|---|
| development | Машина разработчика | Схема строится из моделей, `alembic_version` может отсутствовать |
| test | Прогон тестов | То же; строгие проверки схемы намеренно не блокируют |
| staging | Зеркало боевой: тот же PostgreSQL, обезличенные данные | **Миграция попадает в бой только после наката на staging** |
| production | Боевой контур | Строгий режим: нет `alembic_version` — экземпляр не готов |

Строгость проверок зависит от `APP_ENV`, а не от удачи: в production и staging
«не смог проверить схему» означает «не готов», в development и test — нет.
