# USER_ACCESS_AND_ROLES

## Реальный механизм выдачи доступов
После создания пользователя owner/admin управляет доступами через admin API:
- `GET /api/routes/admin/users/{user_id}/roles` — фактически смонтировано под `/api/v1/...`;
- `POST|PATCH /api/v1/admin/users/{user_id}/roles`;
- `PATCH /api/v1/admin/users/{user_id}/attributes`.

## Что можно выдать
### Роли
Нормализуются через `RoleEnum`. На практике repo поддерживает, среди прочих:
- `owner`
- `admin`
- `ot_pb_lead`
- `ot_specialist`
- `pb_engineer`
- `hr`
- `lawyer`
- `accountant`
- `line_manager`
- `employee`
- `client_admin`
- `client_user`

### Scope attributes
Через `UserAttribute` можно ограничить пользователя по:
- `company_ids`
- `site_ids`
- `project_ids`
- `contractor_ids`

Для текущего repo сценарий branch scope = `site_ids`.

## Practical flow
1. Создать tenant owner через `scripts/bootstrap_tenant.py` или dev admin через env bootstrap.
2. Создать/импортировать пользователя существующим auth/user flow проекта.
3. Назначить роли через `/api/v1/admin/users/{user_id}/roles`.
4. Назначить scope через `/api/v1/admin/users/{user_id}/attributes`.
5. Проверить audit/admin screens и доступ к маршрутам UI.

## Ограничения текущей реализации
- В этой волне документируется и усиливается role/scope issuance; отдельный invitation self-service flow в repo не является fully-closed canonical path.
- Включение/выключение доступа зависит от текущего user lifecycle проекта; для production нужно использовать существующий user active flag и password management policy.
## Canonical user access paths
- Role assignment API: `backend/app/api/routes/admin_users.py`
- RBAC/ABAC policy helpers: `backend/app/core/rbac_abac.py`, `backend/app/core/security.py`
- AuthZ seed/catalog: `backend/app/services/authz_seed.py`

## Core roles seen in repo
- `owner`
- `admin`
- `manager`
- `hr`
- `line_manager`
- OT/PB specializations such as `ot_specialist`, `ot_pb_lead`, `pb_engineer`
- read-only / portal / client roles where implemented

## Issue access to a user
### 1. Create/provision the user
Use the existing tenant user creation path for the environment or bootstrap/import flow already used by the project.

### 2. Assign roles
```http
PATCH /api/v1/admin/users/{user_id}/roles
```
Body example:
```json
{
  "roles": ["owner", "admin"]
}
```

### 3. Restrict scope (tenant/company/site)
```http
PATCH /api/v1/admin/users/{user_id}/attributes
```
Body example:
```json
{
  "company_ids": ["<company-id>"],
  "site_ids": ["<site-id>"],
  "project_ids": [],
  "contractor_ids": []
}
```

## Practical mapping for document workflows
- `owner` / `admin`: bootstrap tenant, manage users, manage templates, issue broad access
- `methodologist` or equivalent document authority role: manage templates and versions
- `doc officer`: prepare/generate documents and operate pipelines
- scoped specialists: constrained with company/site attribute sets

## Audit visibility
Where implemented, owner/admin can inspect audit-oriented endpoints under `/api/v1/audit` and related admin diagnostics.
