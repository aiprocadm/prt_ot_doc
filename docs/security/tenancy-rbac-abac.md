# Tenancy + RBAC + ABAC

## Public routes
Only `/healthz`, `/readyz`, and `/api/v1/auth/*` are public. Any business API request must include `X-Tenant`.

## Actions
Supported actions: `read`, `list`, `create`, `update`, `delete`, `approve`, `sign`, `export`, `admin`.

## Policy rule authoring
1. Declare RBAC permission (`resource:action`) in `ROLE_PERMISSIONS`.
2. Add ABAC predicates in `PolicyEngine._scope_check` using resource attributes (`company_id`, `site_id`, `document_id`, `status`, `risk_level`, `project_id`, `contractor_id`).
3. Deny by default when scope does not match.

## Query scoping
Use `scope_query(...)` from `app.core.db.scoping` in every repository list/read query.

> Never bypass `scope_query` for tenant-scoped entities.

## Audit
- Access decisions are stored in `SecurityAuditLog`.
- Field-level changes can be tracked via `field_level_diff(...)` + `AuditService.log_event(...)`.
