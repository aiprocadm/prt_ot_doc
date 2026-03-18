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
- `page`, `size`, `sort`, фильтры домена через query params.

## Quotas and rate limits
- При лимитах возвращается унифицированная ошибка с типами:
  - `quota_exceeded`
  - `subscription_inactive`
  - `feature_disabled`
- При rate-limit возвращается `429` с retry hints.


## Machine access foundation
- Для machine-to-machine сценариев добавлен tenant-scoped контур `/api/v1/machine-keys` + `/api/v1/public/*`.
- Ключи создаются на tenant уровне, показываются только один раз, имеют scopes, usage counters, revoke metadata и future-ready `rate_limit_per_minute`.
- Аутентификация машинных клиентов выполняется заголовком `X-API-Key`, отдельно от JWT user sessions.

## Stable public slices
- Доступны read-contracts для `employees`, `documents`, `training`, `risks`, `incidents`, `inspections`, `prescriptions`, `notifications`, `reports/exports`, `integrations/webhooks`.
- Все роуты tenant-safe и продолжают требовать `X-Tenant`.
- Ошибки сохраняют structured payload с кодом и сообщением.
