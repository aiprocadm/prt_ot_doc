# Webhooks Runbook

## Verifying signature

1. Read raw request body bytes.
2. Compute `hmac_sha256(secret, raw_body)`.
3. Compare with `X-Signature` (`sha256=<hex>`).

## Required headers

- `X-Event-Id`
- `X-Event-Type`
- `X-Tenant`
- `X-Correlation-Id`
- `X-Signature`

## Delivery behavior

- Dispatcher retries failures with exponential backoff.
- Poison/dead after max attempts.
- Dedup by `(subscription_id, event_id)`.
