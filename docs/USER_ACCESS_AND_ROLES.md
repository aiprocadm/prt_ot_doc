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
