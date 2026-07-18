# Document pipeline jobs

## Status model

`DocumentJob.status` lifecycle: `queued -> running -> success|failed|canceled`.

Each job has step timeline in `document_job_steps` with per-step status:
`queued|running|success|failed|skipped`.

Mandatory steps:
- `render_docx`
- `apply_headers`
- `replace`
- `convert_pdf`

Optional steps:
- `build_zip`
- `send_edo`
- `archive`

## Idempotency semantics

`POST /v1/documents:generate` requires `Idempotency-Key` and `X-Tenant`.

- Same key + same `request_hash` => returns the previously accepted job.
- Same key + different `request_hash` => `409 idempotency_conflict`.

Request hash is calculated from canonical JSON (`sort_keys=True`).

## Retry rules

- `convert_pdf` has timeout budget of 45s and one retry.
- `send_edo` uses retry with exponential-style policy at orchestrator layer.
- validation errors are not retried.

## Adding a new step

1. Add step code in orchestrator mandatory/optional lists.
2. Map artifact kind if step produces file output.
3. Define retry budget in `RETRYABLE_STEPS` if needed.
4. Expose step inputs/outputs in `input_ref`/`output_ref` for timeline UI.
