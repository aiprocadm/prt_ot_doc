# Pipelines / Orchestration v1

## Pipeline profile
`pipeline_profiles.steps` хранит цепочку шагов:

- `render_docx`
- `apply_headers`
- `replace`
- `convert_pdf`
- `build_zip`
- `archive`
- `send_edo`
- `index_content`

При создании профиля валидируются `code` шага и `params_schema` (Pydantic v2).

## Лимиты
`pipeline_profiles.limits`:

- `max_parallel`
- `max_parallel_per_step`

Tenant limiter реализован через Redis semaphore key `pipeline:tenant:{tenant_id}:running`.

## Статусы
Job: `queued|running|success|failed|canceled`

Step: `queued|running|success|failed|skipped|canceled`

## Retry / Restart
- `POST /v1/jobs/{job_id}/retry` — retry failed path.
- `POST /v1/jobs/{job_id}/restart` — requeue с order N.
- transient retry policy: один ретрай для сбойных интеграционных шагов.

## Idempotency
`POST /v1/pipelines/run` требует `Idempotency-Key`; key+request_hash возвращает тот же `job_id`.

## Live status
`GET /v1/jobs/stream` (SSE) отправляет `JobStatusChanged` события.
