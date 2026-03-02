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


## Low-code graph DSL (NEXT-49)
- `graph.nodes[]`: `{id, type, config, retry, timeout_s, on_error, emit_events}`.
- `graph.edges[]`: `{from, to, condition?}` with safe condition evaluator (`==`, `!=`, `in`, `and/or`, numeric compares).
- `graph.inputs` / `graph.outputs`: runtime context contracts.
- Reserved context keys (cannot be overridden by `inputs`): `tenant_id`, `correlation_id`, `job_id`, `run_id`, `artifacts`, `meta`.
- Validator constraints: DAG only (no cycles), reachable terminal nodes, branch nodes require default edge (if conditional edges exist) and at least two outgoing edges, depth and node count limits.
