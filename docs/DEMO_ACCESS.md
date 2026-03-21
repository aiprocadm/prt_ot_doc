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
