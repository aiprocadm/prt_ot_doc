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
