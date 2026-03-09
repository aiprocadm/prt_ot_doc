# CLI (`ptd`)

Основная точка входа: `python -m app.cli.main` (обёртка в корне: `./ptd`).

## Команды
- `ptd render <template_id> <context.json> [--tenant <slug>] [--json]`
- `ptd header <template_name> [--json]`
- `ptd replace <template_name> <placeholder> <value> <output_path> [--json]`
- `ptd pipeline <template_id> <context.json> [--tenant <slug>] [--json]`
- `ptd export --tenant <slug> [--json]`
- `ptd health check [--json]`
- `ptd health release-readiness [--json]`
- `ptd backup [--triggered-by manual|scheduler|ci] [--json]`
- `ptd restore [--mode test|full] [--json]`
- `ptd reindex [--tenant <slug>] [--json]`
- `ptd projections rebuild [--tenant <slug>] [--json]`

## Общие правила
- Для tenant-aware операций используйте `--tenant`.
- Для машинной интеграции используйте режим JSON (`--json`).
- CLI не обходит auth/tenant-правила API; административные служебные команды должны запускаться только в доверенном окружении.

## Коды завершения
- `0` — ok
- `2` — validation
- `3` — resources
- `4` — external services
- `5` — internal
