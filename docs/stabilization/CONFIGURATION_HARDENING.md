# Ужесточение конфигурации

## Переменные окружения и приоритет

`Settings` (pydantic-settings) читает `.env` и процесс env. **Явные аргументы конструктора** должны иметь приоритет над env в типичном сценарии; в тестах при коллизиях использовать `monkeypatch.delenv` для критичных ключей (см. `test_settings_staging_hardening.py`).

## Production (`APP_ENV=production`)

- Обязательны непустые `PRIVATE_KEY_PEM` и `PUBLIC_KEY_PEM` (не dev-пара).
- Запрещены: `SECRET_KEY=change-me`, `POSTGRES_PASSWORD=change_me`, локальные `S3_ACCESS_KEY`/`S3_SECRET_KEY` по умолчанию, `S3_BACKEND=memory`.
- Реализовано в `_ensure_production_secrets` и `_ensure_jwt_keys`.

## Staging (`APP_ENV=staging`)

- Те же ограничения, что и production, для **инфраструктурных** секретов: `SECRET_KEY`, Postgres, S3 (включая запрет `memory` backend).
- **JWT:** как в development — если ключи не заданы, подставляется dev-пара с **warning** в лог. Для боевого staging рекомендуется задать свои PEM.

## Development / test

- Допускаются dev-умолчания; `APP_ENV=test` в CI для pytest.

## bootstrap(role)

- Проверяет непустоту: `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`.
- Ошибки → `SettingsError` (не `RuntimeError`).
- Дополнительно: для `production` и `staging` запрещён `SECRET_KEY=change-me` на этапе bootstrap.

## Рекомендуемый чеклист нового окружения

1. Скопировать `.env.example` → `.env`.
2. Установить уникальные секреты (длина, не из репозитория).
3. Для staging/production: реальный S3-совместимый backend и bucket.
4. Включить JSON-логи в prod: `LOG_JSON=true` (если поддерживается).

## Интеграции (ЭДО HTTP)

- `USE_EDO_INTEGRATION=true` + непустой `EDO_INTEGRATION_BASE_URL` переключает фабрику на `HttpEDOIntegration` (см. `docs/integrations/PRODUCTION_ADAPTERS.md`).
- `EDO_INTEGRATION_API_TOKEN` хранить только в секретах окружения; не коммитить в `.env` репозитория.

## Fail-fast (идеи на следующий этап)

- Проверка доступности Redis/S3 при старте (опционально, с таймаутом).
- Валидация `ALLOWED_HOSTS` / `APP_CORS_ORIGINS` для production (не `*` с credentials).
