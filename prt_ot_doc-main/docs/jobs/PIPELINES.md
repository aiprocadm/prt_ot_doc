# Document Job Pipelines

## Steps
1. `render_docx`
2. `apply_headers`
3. `replace`
4. `convert_pdf`
5. Optional: `build_zip`, `send_edo`, `archive`

## Status model
- Job: `queued -> running -> success|failed|canceled`
- Step: `queued -> running -> success|failed|skipped|canceled`
- Every step stores `attempts`, `started_at`, `ended_at`, `error_code`, `error_payload`.

## Retry rules
- Retry only for job in `failed` or `canceled`.
- Retry increments `attempts` and re-runs steps.
- Step idempotency: if artifact already exists in `document_artifacts` (`job_id+step_code+kind`), step exits as success without duplicating file output.

## Outbox events
- `DocumentGenerated` after successful mandatory pipeline.
- `Exported` after successful ZIP/export stage.
- `Failed` when job ends in failed state.

## Add a new step
1. Add new step code in orchestrator sequence.
2. Decide if mandatory or optional.
3. Define artifact kind mapping (if step emits output).
4. Add retry policy and tests for success/failure transitions.
5. Add/adjust outbox event generation if the step is externally observable.
