# OWNER_ADMIN_ACCESS

## Canonical owner/admin bootstrap paths

### 1. Tenant owner bootstrap
Use the tenant bootstrap script when you need a real owner account for a tenant:

```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py \
  --tenant acme \
  --name "ACME" \
  --owner-email owner@acme.local \
  --owner-password 'ChangeMe123!'
```

Implemented by:
- `scripts/bootstrap_tenant.py`
- `backend/app/services/tenants/bootstrap/service.py`

What the bootstrap creates:
- tenant;
- tenant settings + quota;
- owner user;
- `owner` + `admin` roles for that user;
- base company profile;
- starter packs / presets;
- audit event.

### 2. Dev admin bootstrap
For local development, startup can create an admin automatically:
- env flags: `ADMIN_BOOTSTRAP=true`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`;
- startup hook: `backend/app/api/app.py` -> `bootstrap_admin_user(settings)`.

## How owner/admin logs in
- API login route: `POST /api/v1/auth/login`
- Tenant header/context is required: `X-Tenant: <tenant-slug>`
- Credentials are the email/password passed through bootstrap or env.

## Owner/admin capabilities currently implemented
- assign user roles: `GET|POST|PATCH /api/v1/admin/users/{user_id}/roles`;
- assign ABAC scope attributes: `PATCH /api/v1/admin/users/{user_id}/attributes`;
- manage templates and versions;
- access billing/admin/API-token flows;
- inspect audit/admin diagnostics where implemented.

## How owner issues access to users
1. Provision the tenant and owner via bootstrap.
2. Create/import the user using the project’s current user flow for the environment.
3. Assign roles via `/api/v1/admin/users/{user_id}/roles`.
4. Restrict scope via `/api/v1/admin/users/{user_id}/attributes`.
5. Validate access through `/api/v1/auth/me`, UI route visibility, and audit traces.

## Password and secret handling
- Real passwords must not be committed to git.
- For local/stage use CLI args or env.
- For shared/prod environments use a secret manager / vault.

## Recommended local bootstrap sequence
```bash
alembic -c backend/app/migrations/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py \
  --tenant demo \
  --name "Demo Tenant" \
  --owner-email owner@example.local \
  --owner-password 'ChangeMe123!' \
  --demo
```
