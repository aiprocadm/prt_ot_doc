# AUTHZ: RBAC + ABAC

## Компоненты
- `app/core/rbac_abac.py` — единый policy engine (`authorize`) и query scoping (`scoped_query`).
- `app/models/models.py` — каталог ролей/разрешений (`authz_roles`, `authz_permissions`, `authz_role_permissions`, `authz_user_roles`).
- `app/services/authz_seed.py` — стартовое наполнение ролей и permissions.

## Модель
- RBAC: permission code формата `{resource}:{action}`.
- ABAC scope: `company_id`, `site_id`, `project_id`, `contractor_id`.
- Специальные правила:
  - `auditor_ro` имеет только `read/list`.
  - `client` ограничен клиентскими ресурсами.
  - `contractor_inspector` read-only в пределах своего `contractor_id`/`site_id`.

## API guard
Используйте policy engine перед CRUD-операциями:

```python
actor = actor_from_claims(claims, roles)
decision = policy_engine.authorize(actor, action="read", resource="documents", obj=document, ctx={"company_id": company_id})
if not decision.allowed:
    raise policy_forbidden("Forbidden by policy", correlation_id=trace_id)
```

## Query scoping
Для list endpoint обязательно применять `scoped_query`:

```python
stmt = select(Document).where(Document.tenant_id == tenant_id)
stmt = scoped_query(stmt, model=Document, actor=actor, resource="documents")
```

Если ресурс считается scoped, но у модели нет scope-полей — используется fail-closed и list блокируется.

## Как добавить новый ресурс/action
1. Добавьте resource/actions в `RESOURCE_PERMISSIONS`.
2. Добавьте role mappings в `ROLE_PERMISSIONS`.
3. При необходимости добавьте ресурс в `SCOPED_RESOURCES`.
4. Перезапустите seed (`seed_authz_catalog`) для заполнения `authz_permissions` и `authz_role_permissions`.
5. Добавьте тесты на allow/deny и scoping.
