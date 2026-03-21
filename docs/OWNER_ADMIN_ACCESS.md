# OWNER_ADMIN_ACCESS

## Owner bootstrap (canonical)
Create a real tenant owner using the repo bootstrap flow:

```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py \
  --tenant acme \
  --name "ACME" \
  --owner-email owner@acme.local \
  --owner-password 'ChangeMe123!'
```

Implementation lives in:
- `scripts/bootstrap_tenant.py`
- `backend/app/services/tenants/bootstrap/service.py`

## What the bootstrap creates
- tenant
- tenant settings
- quota row
- owner user
- owner + admin roles for that user
- base company profile
- starter pack and package presets
- audit event for completed bootstrap

## Login
Use the regular tenant-aware login endpoint:
- `POST /api/v1/auth/login`

The owner logs in with the email/password supplied to `scripts/bootstrap_tenant.py`.

## Owner/admin capabilities in repo today
- assign user roles: `/admin/users/{user_id}/roles`
- assign ABAC scope attributes: `/admin/users/{user_id}/attributes`
- access billing, audit, API token and other management endpoints gated by `owner` / `admin`

## Password handling
Do not commit real passwords into the repository.
For local/stage environments, pass them at bootstrap time or via environment/secret manager.

## Recommended local bootstrap sequence
```bash
alembic -c backend/app/migrations/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py --tenant demo --name "Demo Tenant" --owner-email owner@example.local --owner-password 'ChangeMe123!' --demo
```
