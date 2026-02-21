# Tenancy Core

- Все бизнес-роуты `/api/v1/**` (кроме auth/health/docs/openapi) требуют `X-Tenant`.
- Поддерживается `X-Tenant` как `slug`, `code` или `UUID` tenant.
- На каждый запрос tenant-контекст кладётся в `request.state` (id/slug/schema/quota).
- DB использует schema-per-tenant через `search_path` (`<tenant_schema>, public`).

## S3 isolation

- Ключи файлов формируются в tenant namespace: `tenants/{tenant_id}/...`.
- Доступ к signed URL проверяет принадлежность tenant-префиксу.

## Celery isolation

- Роутинг задач по tenant в очереди `tenant.{tenant_id}`.
- Для бизнес-задач без tenant роутинг запрещён (`missing_tenant`).

## Quotas

- Проверки квот реализованы в `app/tenancy_quotas.py`.
- На текущем этапе проверяются: `generations_month`, `jobs`, `storage_bytes`.
- При превышении возвращается `429 quota_exceeded`.
