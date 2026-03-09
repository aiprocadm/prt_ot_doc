# DEMO_TENANT_SETUP

## Команда
- `PYTHONPATH=backend .venv/bin/python scripts/bootstrap_demo_tenant.py --force`

Demo mode:
- использует synthetic данные из `seed/demo/v1/`;
- помечается как `DEMO_DATA`;
- отделён от production bootstrap.
