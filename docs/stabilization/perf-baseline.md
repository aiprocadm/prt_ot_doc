# Performance Baseline (Stabilization)

_Last updated: 2026-04-19._

This file tracks what performance evidence exists now and what baseline is still missing.

## Existing perf tooling and evidence

- Load probe script: `scripts/perf/api_load.py`.
- Usage guidance and target commands: `scripts/perf/README.md`.
- CI currently focuses on correctness (tests/static/compose smoke) in `.github/workflows/ci.yml`; no perf gate job is defined there.

## Baseline command set (from existing scripts)

Use these exact probes to collect baseline numbers per environment:

1. `python scripts/perf/api_load.py --base-url http://localhost:8000 --path /health --requests 100 --concurrency 20`
2. `python scripts/perf/api_load.py --base-url http://localhost:8000 --path /api/v1/templates --tenant demo --requests 100 --concurrency 20`
3. `python scripts/perf/api_load.py --base-url http://localhost:8000 --path '/api/v1/search/suggest?q=doc' --tenant demo --requests 50 --concurrency 10`

## Baseline table (to be filled with measured outputs)

| Endpoint/profile | Requests | Concurrency | Status expectation | p50 | p95 | max | error rate | Evidence artifact |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `/health` | 100 | 20 | 200 | _gap_ | _gap_ | _gap_ | _gap_ | _gap_ |
| `/api/v1/templates` (tenant demo) | 100 | 20 | 200 | _gap_ | _gap_ | _gap_ | _gap_ | _gap_ |
| `/api/v1/search/suggest?q=doc` (tenant demo) | 50 | 10 | 200 | _gap_ | _gap_ | _gap_ | _gap_ | _gap_ |

## Related functional reliability evidence (not perf metrics)

- Job status transitions: `tests/integration/test_job_status_flow.py`.
- Pipeline happy path/idempotency: `tests/integration/test_pipeline_steps_happy_path.py`, `tests/integration/test_pipeline_idempotency.py`.

These tests verify behavior correctness but do **not** establish latency/error budgets.

## Explicit current gaps

- No committed measured baseline artifacts in `docs/stabilization/` yet.
- No threshold-based perf regression gate in `.github/workflows/ci.yml`.
- No environment-specific baseline split (local/staging/pilot).

## Acceptance criteria for this workstream

- Baseline table populated from real command outputs with artifact links.
- At least one non-production environment baseline refreshed on each release-candidate cycle.
- Regression policy declared (e.g., p95 and error-rate thresholds) and linked to an executable check.
