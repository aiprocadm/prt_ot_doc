# DEMO_ACCESS

## Реальный механизм demo access
Demo bootstrapping в repo реализован через:
- env flags: `DEMO_BOOTSTRAP`, `DEMO_TENANT_ID`, `DEMO_COMPANY_NAME`, `DEMO_SITE_NAME`;
- startup hook в `backend/app/api/app.py`;
- script: `PYTHONPATH=backend python scripts/bootstrap_demo_tenant.py --force`.

## Demo tenant
По умолчанию demo tenant slug: `demo`.

Создаётся:
- tenant;
- company;
- site;
- department;
- position;
- sample person;
- sample training course;
- starter packs.

## Как поднять demo локально
1. Включить dev/test env.
2. Задать `DEMO_BOOTSTRAP=true`.
3. Запустить API или вручную выполнить:
   `PYTHONPATH=backend python scripts/bootstrap_demo_tenant.py --force`
4. Убедиться, что запросы идут с `X-Tenant: demo`.

## Credentials
В репозитории demo password не захардкожен отдельным безопасным пользователем. Для demo-входа используйте owner/admin bootstrap вместе с demo tenant, либо создайте пользователя через tenant bootstrap/admin flow.

## Ограничения demo
- Demo — synthetic dataset для walkthrough и smoke.
- Demo bootstrap не должен считаться production provisioning.
- Не все vertical flows seeded одинаково глубоко; часть сценариев требует ручного создания сущностей после bootstrap.
## Demo tenant purpose
The repository contains a deterministic demo tenant intended for walkthroughs, smoke checks and local/stage validation of document workflows.

## Canonical bootstrap
```bash
PYTHONPATH=backend .venv/bin/python scripts/bootstrap_demo_tenant.py --force
```

## What demo bootstrap creates
- tenant slug from `Settings.demo_tenant_id` (default demo)
- demo company
- demo site/branch (`Site` model)
- baseline employee/course entities
- default starter packs and demo-like records used in walkthroughs

Implementation: `scripts/bootstrap_demo_tenant.py`, `backend/app/services/demo_bootstrap.py`.

## Login / route pattern
Auth is tenant-aware. Use the regular login route and pass/select the demo tenant slug configured for the environment.

- API login route: `/api/v1/auth/login`
- Frontend login screen: standard app login page
- Demo tenant slug: environment-driven (`demo` by default)

## Credentials
Static demo credentials are **not stored in git**.
Use one of these safe options:
1. bootstrap a dedicated owner account with `scripts/bootstrap_tenant.py --demo`; or
2. provision a demo user through the regular admin/owner flow in the demo tenant.

## Demo limitations
- intended for non-production data only;
- data is synthetic / seeded;
- branch is represented as `Site` in code;
- some external integrations require separate secrets and are not auto-enabled by demo bootstrap.

## Demo-enabled modules
The demo tenant is suitable for showing at least:
- templates and document generation;
- company/site-scoped branding;
- packs;
- training foundation;
- incidents / inspections / risks baseline screens;
- audit-backed admin flows already present in the tenant.
