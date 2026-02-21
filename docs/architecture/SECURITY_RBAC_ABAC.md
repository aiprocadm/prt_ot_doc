# SECURITY: RBAC + ABAC

## RBAC

- Base roles are defined in `RoleEnum` and can be combined via `user_role` assignments.
- Administrative endpoints under `/api/v1/admin/*` are restricted to `admin` and `owner` roles.
- Role checks are enforced server-side via `rbac(...)` dependencies.

## ABAC

Attributes used by policy checks:
- `company_id`
- `site_id`
- `project_id`
- `contractor_id`
- `status`
- `risk_level`

Rules:
- company/site/project/contractor scope must match actor attribute arrays when arrays are set.
- status `archived` and `signed` are immutable for non-admin/non-owner update flows.
- `risk_level=high` allows approve/sign only for `ot_head`, `ot_pb_lead`, `admin`, `owner`.

## Query-level enforcement

- `apply_abac_filters(query, actor, model)` adds mandatory SQL filters when model has matching scoped columns.
- Repository list methods must call this helper to avoid accidental over-fetch.
