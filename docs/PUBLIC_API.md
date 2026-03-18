# Public API v1

## Base path and tenant scoping
- Все публичные роуты идут через `/api/v1`.
- Для бизнес-роутов обязателен заголовок `X-Tenant`.

## Authentication
- JWT сессии для пользовательских запросов.
- API tokens для server-to-server интеграций (`/api/v1/api-tokens`).
- Raw API token показывается только один раз при создании.

## Idempotency
- Для write-операций с побочными эффектами используйте `Idempotency-Key`.
- Одинаковый ключ и payload -> повторяемый ответ.
- Одинаковый ключ и другой payload -> `409`.

## Pagination / filtering / sorting
- Для machine/public slice используется единый envelope: `limit`, `offset`, `sort_by`, `sort_order`, `total`, `items`.
- Фильтрация по `status` и базовый `q`-поиск доступны там, где модель поддерживает соответствующие поля.

## Quotas and rate limits
- При лимитах возвращается унифицированная ошибка с типами:
  - `quota_exceeded`
  - `subscription_inactive`
  - `feature_disabled`
- При rate-limit возвращается `429` с retry hints.


## Machine access foundation
- Для machine-to-machine сценариев добавлен tenant-scoped контур `/api/v1/machine-keys` + `/api/v1/public/*`.
- Ключи создаются на tenant уровне, показываются только один раз, имеют scopes, usage counters, revoke metadata и future-ready `rate_limit_per_minute`.
- Поддерживается rotation foundation: `POST /api/v1/machine-keys/{id}/rotate` деактивирует старый ключ, выдает новый секрет и сохраняет метаданные ротации.
- Аутентификация машинных клиентов выполняется заголовком `X-API-Key`, отдельно от JWT user sessions.

## Stable public slices
- Доступны read-contracts для `employees`, `documents`, `training`, `risks`, `incidents`, `inspections`, `prescriptions`, `notifications`, `reports/exports`, `integrations/webhooks`.
- Все роуты tenant-safe и продолжают требовать `X-Tenant`.
- Ошибки сохраняют structured payload с кодом и сообщением.
- Webhook subscriptions management foundation переиспользует tenant-scoped registry `/api/v1/webhooks/endpoints`, а machine/public slice `/api/v1/public/integrations/webhooks` дает стабильный read-contract для интеграционных каталогов.
