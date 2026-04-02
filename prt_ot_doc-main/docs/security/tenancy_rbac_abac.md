# Tenancy + RBAC/ABAC enforcement

## Обязательный `X-Tenant`

`X-Tenant` обязателен для всех business-route (`/api/v1/*`), кроме:

- `/api/v1/auth/*`
- `/healthz`, `/readyz`, `/docs`, `/openapi.json`

Если заголовок отсутствует, middleware возвращает `400` с кодом `tenant_required`.

## Проверка tenant

1. Middleware читает tenant из заголовка.
2. В `public`-контуре проверяет существование tenant в таблице `tenant`.
3. Если не найден — `tenant_not_found`.
4. Если tenant неактивен — `tenant_disabled`.

## Schema routing

Для каждого запроса с tenant-контекстом создаётся tenant-scoped session (`get_tenant_session`),
а `search_path` выставляется как `"<tenant_schema>", "public"`.

## RBAC

- Права формируются на основании ролей и карты `ROLE_PERMISSIONS`.
- Эндпоинт `GET /api/v1/auth/me/permissions` возвращает:
  - `roles`
  - `permissions` (в формате `resource.action`)
  - `abac_scopes`

### Как добавить permission

1. Добавить действие в `RESOURCE_PERMISSIONS`.
2. Раздать коды в `ROLE_PERMISSIONS`.
3. Применить guard на endpoint.

## ABAC

Атрибуты для ABAC:

- `company_id`
- `site_id`
- `project_id`
- `contractor_id`
- `status`
- `risk_level`

### Как писать ABAC-фильтры

Используйте `scoped_query(...)` / `apply_abac_filters(...)` на уровне SQL запроса:

- фильтры по company/site/project/contractor должны применяться в SQL;
- пост-фильтрация в Python не допускается.

### Пример policy rule

- `executor` с `project_ids=[A]` может видеть только ресурсы с `project_id=A`.
- пользователь с `max_risk_level=2` не может читать ресурсы с `risk_level>2`.
