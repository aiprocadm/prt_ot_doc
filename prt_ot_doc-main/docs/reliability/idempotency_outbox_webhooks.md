# Reliability Core: Idempotency + Outbox + Webhooks

## Idempotency keys
- Required for mutation endpoints like `POST /documents/generate` and `POST /packs/run`.
- Scope: `(tenant, endpoint, key)`.
- Request hash uses canonical request JSON SHA-256.
- Reuse rules:
  - same key + same hash → stored response is returned.
  - same key + different hash → `409 idempotency_conflict`.
- Stored payload includes both HTTP status code and body.

## Outbox pattern
- Domain transaction and outbox insert are done in the same DB transaction.
- Publisher worker processes pending rows with retry scheduling.
- Delivery semantics: at-least-once.
- Duplicate delivery protection is implemented by `(destination, idempotency_key)` and successful delivery checks.

## Retry/backoff
- Exponential backoff with jitter.
- Configurable by:
  - `OUTBOX_RETRY_BACKOFF_SECONDS`
  - `OUTBOX_RETRY_BACKOFF_MAX_SECONDS`
  - `OUTBOX_MAX_ATTEMPTS`
- Exhausted attempts are moved to dead/poison state and logged for alerting.

## Correlation
- `X-Correlation-Id` is the primary tracing header.
- Correlation id is propagated from API to outbox payload and webhook headers.

## Adding a new event
1. Add event type and payload schema in `app/services/events.py`.
2. Enqueue event through `OutboxService.enqueue(...)` in domain service transaction.
3. Ensure webhook subscriptions exist for the new event type.
4. Add tests for routing and retry behavior.
