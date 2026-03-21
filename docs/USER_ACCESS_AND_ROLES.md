# USER_ACCESS_AND_ROLES

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
