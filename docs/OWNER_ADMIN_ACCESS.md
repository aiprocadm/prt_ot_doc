# OWNER_ADMIN_ACCESS

## Platform owner / tenant owner
В repo есть два реальных bootstrap-механизма.

### 1. Dev admin bootstrap
Используется для локального development:
- env: `ADMIN_BOOTSTRAP=true`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_TENANT`;
- startup hook: `bootstrap_admin_user(settings)`.

### 2. Tenant owner bootstrap
Используется для реального owner flow аренды:
```bash
PYTHONPATH=backend python scripts/bootstrap_tenant.py \
## Owner bootstrap (canonical)
Create a real tenant owner using the repo bootstrap flow:

```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py \
  --tenant acme \
  --name "ACME" \
  --owner-email owner@acme.local \
  --owner-password 'ChangeMe123!'
```

Что создаётся:
- tenant;
- tenant settings;
- tenant quota;
- owner user;
- owner/admin roles;
- company profile;
- starter pack;
- package presets;
- audit event.

## Owner права
Owner bootstrap выдаёт как минимум `owner` и `admin` роли одной учётной записи.
Это даёт доступ к:
- админскому управлению ролями;
- tenant-scoped user access management;
- billing/admin/API-token flows;
- audit / outbox / diagnostic screens;
- document/template operations.

## Как войти
1. Использовать email/password, созданные bootstrap script/env.
2. Передавать правильный `X-Tenant` header для tenant scope.
3. Для local admin bootstrap tenant выбирается из `ADMIN_TENANT`.

## Если пароль нельзя хранить в repo
Так и должно быть. Используйте:
- env variables для dev admin bootstrap;
- CLI/script bootstrap для стендов;
- vault/secret manager для production secrets.
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
