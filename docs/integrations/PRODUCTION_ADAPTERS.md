# Production integration adapters

## Maturity table (actual)

| Adapter | Maturity | Notes |
|---|---|---|
| EDO | `production-ready` | Current production-capable path (`HttpEDOIntegration`) |
| 1C | `pilot` | Contract-only pilot adapter, no external transport |
| FRDO | `pilot` | Contract-only pilot adapter, no external transport |
| EISOT | `pilot` | Contract-only pilot adapter, no external transport |

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

These are intentionally **pilot** adapters (contract-only + in-memory behavior) selected by:

- `USE_1C_INTEGRATION=true` → `PilotAccountingIntegration`
- `USE_FRDO_INTEGRATION=true` → `PilotFRDOIntegration`
- `USE_EISOT_INTEGRATION=true` → `PilotEISOTIntegration`

They provide explicit `feature_flag` metadata in responses and use normalized error contract (`IntegrationContractError` / `IntegrationErrorContract`) for validation failures.

## Cache note

Integration factories are `@lru_cache()`; restart workers or call `reset_integration_providers()` after configuration changes in long-lived processes.
