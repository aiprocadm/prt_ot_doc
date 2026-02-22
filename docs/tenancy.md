# Tenancy

## X-Tenant guard

For business routes under `/api/v1/*` (`/healthz`, `/readyz`, `/api/v1/auth/*` are exempt), header `X-Tenant` is mandatory.

If missing, API returns:

```json
{
  "code": "TENANT_REQUIRED",
  "message": "X-Tenant header is required"
}
```

## Schema routing

Tenant DB operations are executed with tenant search path:

- request sessions configure `search_path=<tenant_schema>,public`
- `with_tenant_db(session, tenant_schema)` enforces `SET LOCAL search_path`

## S3/MinIO isolation

Object keys are tenant-prefixed:

- format: `tenants/<tenant_slug>/<...>`
- helper: `tenant_s3_key(tenant_id, path)`

## Quotas

Per-tenant quotas are enforced by `tenant_quotas` and used for:

- `max_parallel_jobs`
- `max_doc_generations_per_month`
- `max_storage_mb`

## Quick curl

```bash
curl -H "Authorization: Bearer <token>" -H "X-Tenant: acme" http://localhost:8000/api/v1/tenants
```
