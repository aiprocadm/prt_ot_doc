# RBAC + ABAC policy engine

## Модель ролей

Система использует единый движок `PolicyEngine` (`app/core/rbac_abac.py`) с нормализованными ролями:

- owner/admin
- methodist/lawyer
- project_manager
- executor
- clerk
- instructor/student
- hse_head/hse_specialist
- fire_engineer
- ecologist
- hr
- accountant
- line_manager
- client
- auditor_ro
- inspector_contractor

Для совместимости поддерживаются алиасы (`tenant_owner -> owner`, `teacher -> instructor`, и т.д.).

## ABAC-атрибуты

ABAC применяет ограничения по:

- `company_id`
- `site_id`
- `project_id`
- `contractor_id`
- `status` (через `allowed_statuses`)
- `risk_level` (через `max_risk_level`)

Проверки работают на двух уровнях:

1. API-level (через вызов policy engine / guard dependency)
2. Query-level (через `scoped_query(...)` + обязательные SQL-фильтры)

## Как добавить новый endpoint

1. На API-слое получить actor (`actor_from_claims`) и проверить `policy_engine.can(...)`.
2. Если `decision.allowed == False`, вернуть `policy_forbidden(decision.reason)`.
3. Любой SELECT к доменным моделям строить через `scoped_query(...)`.
4. В loader для ресурса сначала применить query scoping, затем загрузить объект.

## Пример политики для новой сущности

1. Добавить ресурс и действия в `RESOURCE_PERMISSIONS`.
2. Добавить права по ролям в `ROLE_PERMISSIONS`.
3. Внести ресурс в `SCOPED_RESOURCES`, если нужен fail-closed режим.
4. Для моделей без scope-колонок использовать adapter/join на родителя со scope-полями.

## Guard rails

- В CI и pre-commit включена проверка `scripts/ci/check_scoped_queries.py`, запрещающая `session.query(...)` в backend-коде.
- Это уменьшает риск обхода обязательного `scoped_query(...)`.
