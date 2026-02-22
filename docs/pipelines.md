# Pipelines (NEXT-26)

## Step order
Default document pipeline:
1. `render_docx`
2. `apply_headers`
3. `replace`
4. `convert_pdf`
5. optional: `build_zip`, `verify_signature`, `send_edo`, `archive`

## Job statuses
`queued -> running -> success|failed|canceled`

## Step statuses
`queued|running|success|failed|canceled|skipped`

## Idempotency
Endpoints require `Idempotency-Key` and persist hash+response in `idempotency_keys`.
Same key + same hash returns cached response, different hash returns 409.

## Retry/cancel/rerun
- `POST /v1/jobs/{id}:cancel`
- `POST /v1/jobs/{id}:retry` with body `{ "retry_failed_only": true|false }`
- `POST /v1/jobs/{id}/steps/{step}:rerun`

## Logs
`job_logs` keeps timeline entries with fields:
`timestamp, level, message, step_name, meta_json`.
