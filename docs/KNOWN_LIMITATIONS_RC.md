# KNOWN LIMITATIONS (RC)

## Backend / migrations
- Полный `alembic upgrade` в SQLite (dockerless) ограничен историческими ревизиями с PostgreSQL-типом `JSONB`.
- Для release smoke в локальном контуре используется fallback-gate вместо полного migration path.

## External integrations
- В текущем окружении отсутствует `soffice`, поэтому PDF-конвертация не эквивалентна production-контуру LibreOffice.
- Для отдельных бизнес-флоу (полный replace-chain, интеграционные подписи/ЭДО и т.п.) нужен внешний интеграционный стенд.

## Frontend / test quality
- Тестовый прогон frontend стабилен по exit-code, но содержит много предупреждений React `act(...)`.
