# Tenancy (X-Tenant + schema-per-tenant)

## Создание tenant
- Tenant создаётся в control-plane таблице `public.tenant`.
- Для tenant создаются:
  - `schema_name` (пример: `tenant_<slug>`),
  - `s3_prefix` (по умолчанию `tenant.id`),
  - запись `tenant_settings`.
- Квоты хранятся в `tenant_quotas`.

## X-Tenant
- Заголовок `X-Tenant` обязателен для бизнес-роутов.
- Поддерживается значение:
  - UUID tenant,
  - slug tenant.
- Middleware резолвит tenant и кладёт контекст в `request.state`:
  - `tenant_id`, `tenant_schema`, `tenant_s3_prefix`, `tenant_quota`.

## Public routes
Не требуют `X-Tenant`:
- `/healthz`, `/readyz`
- `/api/v1/auth/*`
- `/api/v1/docs`, `/api/v1/openapi.json`

## Как писать новые endpoint-ы
- Для бизнес API использовать tenant-aware dependency `get_tenant_record` + `get_session`.
- Для операций файлов использовать ключи только через tenant prefix: `{s3_prefix}/...`.
- Для запуска генераций/джобов обязательно вызывать quota checks.
