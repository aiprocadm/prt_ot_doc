# Tenancy architecture

- Header `X-Tenant` is mandatory for business routes; middleware validates tenant existence/active status.
- DB isolation uses PostgreSQL schemas with `search_path = tenant_<slug>, public` for tenant requests.
- Shared/public tables: `tenant`, `tenant_quotas`, `tenant_counters`, outbox/idempotency tables.
- Tenant data tables remain in tenant schema via `TenantBase` metadata.
- New tenant creation flow:
  1. Insert row into `tenant`.
  2. Create schema `tenant_<slug>`.
  3. Apply tenant metadata tables via ORM bootstrap (`create_all`) and Alembic for shared tables.
- Object storage isolation is prefix-based: `<tenant_slug>/<object_key>`; download presign verifies prefix ownership.
- Quotas:
  - `max_parallel_jobs` limits queued/running document jobs per tenant.
  - `max_doc_generations_per_month` enforced by `tenant_counters` (`yyyymm`).
