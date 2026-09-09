# CLI (`ptd`)

Основная точка входа: `python -m app.cli.main` (обёртка в корне: `./ptd`).

## Команды
- `ptd render <template_id> <context.json> [--tenant <slug>] [--json]`
- `ptd header <template_name> [--json]`
- `ptd replace <template_name> <placeholder> <value> <output_path> [--json]`
- `ptd pipeline <template_id> <context.json> [--tenant <slug>] [--json]`
- `ptd health check [--json]`
- `ptd health release-readiness [--json]`
- `ptd reindex [--tenant <slug>] [--json]` — пересобирает поисковый снимок
  ЗДЕСЬ И СЕЙЧАС (та же пересборка, что у ночного тика `search.reindex.tick`);
  без `--tenant` — по всем активным арендаторам. В ответе `rebuilt` — сколько
  записей в снимке.
- `ptd projections rebuild [--tenant <slug>] [--json]` — то же для read
  model'ов (пакеты, соответствие по людям, площадки, кабинет клиента).

### Команды без работы за ними (срез-130)

Эти команды остаются в списке ради совместимости вызовов, но **ничего не
делают и не притворяются**: отвечают `status: not_implemented` с причиной и
кодом возврата `6`. До среза-130 они печатали `queued`/`scheduled` и выходили
с нулём — ночной скрипт на них давал зелёный отчёт о резервных копиях,
которых не существует.

- `ptd export --tenant <slug> [--json]` — выгрузками занимается центр экспорта
  в API.
- `ptd backup [--triggered-by manual|scheduler|ci] [--json]` — резервным
  копированием продукт не управляет: снимки базы и хранилища делает тот, кто
  их держит.
- `ptd restore [--mode test|full] [--json]` — восстановлением продукт не
  управляет; учение проверяется скриптом `scripts/restore_drill.py`.

## Общие правила
- Для tenant-aware операций используйте `--tenant`.
- Для машинной интеграции используйте режим JSON (`--json`).
- CLI не обходит auth/tenant-правила API; административные служебные команды должны запускаться только в доверенном окружении.

## Коды завершения
- `0` — ok
- `2` — validation
- `3` — resources (в т.ч. «база недоступна или не мигрирована» у `reindex` и `projections rebuild`)
- `4` — external services
- `5` — internal
- `6` — команда есть, работы за ней нет (`not_implemented`)
