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
