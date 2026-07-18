# USER_ACCESS_AND_ROLES

## Canonical access-management API
Owner/admin manages user access through:
- `GET /api/v1/admin/users/{user_id}/roles`
- `POST /api/v1/admin/users/{user_id}/roles`
- `PATCH /api/v1/admin/users/{user_id}/roles`
- `PATCH /api/v1/admin/users/{user_id}/attributes`

Canonical implementation:
- `backend/app/api/routes/admin_users.py`
- `backend/app/schemas/admin_user.py`

## Roles currently visible in repo
Normalized through `RoleEnum`. Common roles include:
- `owner`
- `admin`
- `manager`
- `hr`
- `line_manager`
- `ot_pb_lead`
- `ot_specialist`
- `pb_engineer`
- `employee`
- `client_admin`
- `client_user`

## Scope restriction / ABAC attributes
`UserAttribute` currently supports:
- `company_ids`
- `site_ids`
- `project_ids`
- `contractor_ids`

For the current repo, branch scope maps to `site_ids`.

## Practical issuance flow
1. Create a tenant owner via `scripts/bootstrap_tenant.py` or a dev admin via bootstrap env.
2. Provision/import the target user using the environment’s current user flow.
3. Assign one or more roles via `/api/v1/admin/users/{user_id}/roles`.
4. Restrict scope with `/api/v1/admin/users/{user_id}/attributes`.
5. Verify effective access through `/api/v1/auth/me`, UI route visibility, and audit traces.

## Example: assign roles
```http
PATCH /api/v1/admin/users/{user_id}/roles
```

```json
{
  "roles": ["owner", "admin"]
}
```

## Example: restrict company/site scope
```http
PATCH /api/v1/admin/users/{user_id}/attributes
```

```json
{
  "company_ids": ["<company-id>"],
  "site_ids": ["<site-id>"],
  "project_ids": [],
  "contractor_ids": []
}
```

## Document-workflow mapping
- `owner` / `admin`: broad tenant management, user access issuance, templates, billing, diagnostics;
- methodologist-equivalent roles: maintain templates and template versions;
- doc officer-equivalent roles: prepare/generate documents and run document flows;
- scoped specialists: restricted with company/site attribute sets.

## Current limitations
- invitation/self-service onboarding is not yet the canonical closed loop in repo;
- enable/disable and password lifecycle depend on the current user model and deployment policy;
- scope is attribute-based, so future waves can refine with richer org/branch abstractions without breaking current flows.

## Current wave note
- No role definitions were changed in this wave.
- The hardening slice preserved existing tenant-aware execution semantics and avoided widening access in document/pipeline flows.
