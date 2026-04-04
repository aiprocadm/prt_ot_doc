# Production integration adapters

## EDO (HTTP)

When `USE_EDO_INTEGRATION=true` and `EDO_INTEGRATION_BASE_URL` is set, the factory returns `HttpEDOIntegration` instead of the in-memory stub.

| Variable | Purpose |
|----------|---------|
| `EDO_INTEGRATION_BASE_URL` | Operator HTTP root (no trailing slash required) |
| `EDO_INTEGRATION_API_TOKEN` | Optional `Authorization: Bearer …` |
| `EDO_INTEGRATION_TIMEOUT_SECONDS` | Client timeout (default 30) |
| `EDO_INTEGRATION_OUTBOUND_PATH` | POST path for outbound documents (default `/v1/outbound/documents`) |

**Outbound JSON body:** `{ "filename", "content_base64", "metadata" }`.  
**Response:** JSON with `id` or `external_id` and optional `status`.

**Health:** `GET {base}/health` (non-5xx counts as healthy).

If `USE_EDO_INTEGRATION` is true but the base URL is empty, the **stub** adapter is used (non-production / dev).

## 1C / FRDO / EISOT

Still delivered via stub/disabled implementations until dedicated HTTP adapters and env contracts are added. Extend `app/services/integrations/factory.py` using the same pattern as EDO.

## Cache note

Integration factories are `@lru_cache()`; restart workers or call `reset_integration_providers()` after configuration changes in long-lived processes.
