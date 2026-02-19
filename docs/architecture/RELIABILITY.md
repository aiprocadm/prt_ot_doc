# Reliability

## Idempotency-Key

- Supported for critical POST endpoints via `Idempotency-Key` header.
- Key scope is `(tenant_id, endpoint, key)`.
- Reusing same key with same request hash returns stored payload.
- Reusing same key with different request hash returns `409 idempotency_conflict`.

## Outbox

Outbox entries are created inside the same transaction as business operations.
Dispatcher retries failed entries with backoff and moves exhausted records to poison/dead status.

## Webhooks

Tenant subscriptions are stored in `webhook_subscription`.
Each delivery is tracked in `webhook_delivery` for deduplication and audit.

### Signature

`X-Signature: sha256=<hex(hmac_sha256(secret, raw_body))>`

## Retry/Poison

- Retryable statuses: timeout/connection/5xx/429.
- Non-retryable statuses are marked dead immediately.
- Max attempts controlled via settings.
