# CLI (`ptd`)

Основная точка входа: `python -m app.cli.main`.

## Команды
- `ptd render`
- `ptd header`
- `ptd replace`
- `ptd pipeline`

## Общие правила
- Для tenant-aware операций используйте `--tenant`.
- Поддерживайте трассировку через correlation id в внешнем оркестраторе.
- Для машинной интеграции используйте JSON вывод (`--json` в следующих итерациях).

## Exit codes roadmap
- `0` ok
- `2` validation
- `3` resources
- `4` external services
- `5` internal
