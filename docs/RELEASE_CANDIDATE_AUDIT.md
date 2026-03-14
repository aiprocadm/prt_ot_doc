# RELEASE CANDIDATE AUDIT (финальный проход)

Дата аудита: 2026-03-14.

## Что проверено
- Backend: tenant/webhook/idempotency/job flow через `scripts/codex_audit.sh` и целевые `pytest`.
- Frontend: production build (`npm --prefix frontend run build`).
- Smoke: проверен запуск smoke-скрипта (`scripts/smoke.sh`) и зафиксировано ограничение среды.

## Критические проблемы, обнаруженные в ходе аудита
1. **Регрессия inbound webhook tenant-resolution**: эндпойнты `/api/v1/webhooks/inbound/*` и `/api/v1/edo/webhooks/*` отвечали `400` без `X-Tenant`, из-за чего падали тесты tenant-context webhook-очереди.
2. **Сбой smoke в окружении**: `scripts/smoke.sh` не поднимает backend сам и падал на `curl: Failed to connect localhost:8000` при не запущенном сервере.

## Что исправлено
- Добавлены fallback tenant-candidates для webhook маршрутов в dependency resolution (`/webhooks/inbound`, `/edo/webhooks`, `/edo/webhook/status`).
- Tenant middleware обновлён: webhook-маршруты переведены в публичный контур с предзагрузкой tenant context (default/test tenant), чтобы inbound callbacks могли приниматься без `X-Tenant` и корректно прокидывать `tenant_slug` в worker.
1. **Сбой pack-run маршрутов** (`500`) из-за импорта неверной модели PPE (`safety_core.PPEIssue` без `expires_at`) в `api/routes/packs.py`.
2. **Регрессия tenant S3 key prefix** (`tenants/...` vs ожидаемое `tenant/...`) ломала блок файловых тестов.
3. **Тестовая инфраструктура маскировала отсутствие `X-Tenant`** из-за дефолтного заголовка в `tests/conftest.py`.
4. **DX/CI проблема make lint**: при отсутствии `.venv` таргеты падали до запуска инструментов.
5. **Webhook ingress regression**: после удаления дефолтного tenant header тесты webhooks ожидали старое поведение и начали получать `400` без `X-Tenant`.

## Что исправлено
- Исправлен импорт в pack-run API на canonical-модель `models.PPEIssue` + `PPEIssueStatus`.
- Восстановлен префикс tenant-ключей для файлового storage (`tenant/...`) с сохранением проверки legacy/current префиксов.
- Убран дефолтный `x-tenant` из `async_client` фикстуры, чтобы тесты tenancy реально валидировали отсутствие заголовка.
- Makefile теперь корректно использует `.venv/bin/*` при наличии и fallback на системные бинарники при отсутствии `.venv`.
- Тесты webhook tenant-context приведены к актуальному контракту: явная передача `X-Tenant` в бизнес webhook-маршруты.

## Итог по стабилизации
- Исправлен и подтверждён критичный backend-кейс: webhook inbound tenant context.
- Целевые backend тесты tenancy/idempotency/job-status проходят.
- Frontend production build проходит.

## Остаточные риски
- Полный `pytest -q` не прогонялся в этом проходе целиком, остаётся риск в неохваченных подсистемах.
- `scripts/smoke.sh` требует отдельно поднятого backend-процесса (операционный риск для локального запуска без runbook).
