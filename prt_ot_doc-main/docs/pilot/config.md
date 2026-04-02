# Pilot configuration profile

Этот документ описывает, как применять `docs/examples/.env.pilot.example` для пилотного запуска.

## Цели профиля

- Предсказуемые лимиты и таймауты.
- Включённые метрики и логирование.
- Готовые шаблоны webhook/notification-конфигурации.

## Как использовать

1. Скопируйте `docs/examples/.env.pilot.example` в `.env` (или в секреты окружения деплоя).
2. Заполните реальные значения для:
   - `DATABASE_URL`, `POSTGRES_*`.
   - `S3_*`.
   - `SECRET_KEY`, `PRIVATE_KEY_PEM`, `PUBLIC_KEY_PEM`.
   - `REDIS_*`, `RATE_LIMIT_STORAGE_URI`, `CLAMAV_*`.
   - webhook URL-ы.
3. Проверьте, что `APP_TRUSTED_HOSTS` и `APP_CORS_ORIGINS` соответствуют домену пилотного клиента.

## Рекомендуемые значения (pilot-ready)

- `APP_ENV=production`, `APP_DEBUG=false`.
- `LOG_JSON=true` для централизованного логирования.
- `ENABLE_METRICS=true` для мониторинга (см. `docs/ops/observability.md`).
- `RATE_LIMIT_*` на уровне, который защищает от ошибок оператора.
- `OUTBOX_MAX_ATTEMPTS=10`, чтобы ретраи не зацикливались бесконечно.
- `PDF_FALLBACK_MODE=auto`, чтобы исключить пропуски при генерации PDF.

## Примеры webhook-настроек

В `docs/examples/.env.pilot.example` заданы примеры:
- `WEBHOOK_URLS_DOCUMENT_*` — события документов.
- `WEBHOOK_URLS_TRAINING_*` — события обучения.

Если для пилота не нужны внешние интеграции, оставьте эти поля пустыми.

## Контрольные проверки перед запуском

- Настройки совпадают с `docs/pilot/scenarios.md` и `docs/ops/failure-scenarios.md`.
- Убедитесь, что `WORKER_QUEUES` содержит `pdf` и `default`.
- Проверьте доступность хранилища и Redis до запуска приложения.
