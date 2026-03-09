# TENANT_ONBOARDING

Симптомы: tenant не проходит initial setup.

Проверки:
- bootstrap summary
- `tenant.settings.bootstrap_state`
- audit `tenant.bootstrap.completed`

Действия: повторный idempotent bootstrap, только через script/CLI.
