# KNOWN_LIMITATIONS

## Acceptable for pilot
- Не все enterprise-блоки имеют полную E2E автоматизацию; часть проверок остаётся на smoke/manual уровне.
- Набор PWA/offline ограничен текущими сценариями синхронизации.
- Наблюдаются SQLAlchemy warnings в некоторых risk relationships (`overlaps`) — не блокирует pilot, но требует рефакторинга.

## Not acceptable for prod
- Нестабильность кейса `packs/run` idempotency (локально воспроизводимый 500 в тесте `test_pack_run_idempotency`).
- Неполная матрица regression-тестов по leakage для search/export/portal edge-cases.
- Недостаточно формализованы backup/restore drills как регулярная проверка с критериями pass/fail.
