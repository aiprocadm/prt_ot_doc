# TENANT_BOOTSTRAP_RUNBOOK

## Команда
- `PYTHONPATH=backend .venv/bin/python scripts/bootstrap_tenant.py --tenant <slug> --name "<name>" --owner-email <email> [--dry-run] [--demo]`

## Что делает
1. Создаёт tenant и schema.
2. Создаёт tenant settings + quota.
3. Создаёт owner admin user и базовые роли.
4. Применяет starter pack и package presets.
5. Пишет audit event `tenant.bootstrap.completed`.

## Гарантии
- Идемпотентно (повторный запуск переиспользует сущности).
- Безопасный `--dry-run` с JSON summary.
- Аудитируемо.
