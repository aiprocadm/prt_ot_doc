# Perf / load foundations (release candidate)

These probes are intentionally lightweight and reproducible in a pilot or staging stand. They are not a substitute for a full performance lab, but they give a stable baseline for hot-path review and async reliability checks.

## Deterministic harness inputs

The canonical deterministic profiles live in `scripts/perf/scenarios.json`:

- Fixed dataset assumptions (`demo` tenant, stable corpus, clean snapshot before run).
- Fixed concurrency and request counts for:
  - `pr_smoke`
  - `nightly_baseline`

Use these values directly in CI/workflows to avoid drift from ad-hoc command tuning.

## Single-endpoint probe command

```bash
python scripts/perf/api_load.py \
  --base-url http://localhost:8000 \
  --path /api/v1/templates \
  --tenant demo \
  --requests 60 \
  --concurrency 12 \
  --expect-status 200 \
  --max-error-rate 0.02 \
  --min-throughput 18 \
  --max-p95-ms 500 \
  --max-p99-ms 1000 \
  --output-json artifacts/perf/templates-smoke.json
```

The script now emits:

- `p50/p95/p99` latency
- throughput (requests/sec)
- error-rate
- threshold gate PASS/FAIL (process exits non-zero on failure)
- optional JSON artifact output for trend storage

## Critical flow mapping

The baseline profile covers these critical paths:

1. Auth/session readiness (`/health`) — prerequisite for token refresh and protected requests.
2. Dashboard summary (`/api/v1/dashboard/summary`).
3. List endpoint (`/api/v1/templates`).
4. Search suggest (`/api/v1/search/suggest?q=doc`).
5. File registry/list as download readiness proxy (`/api/v1/files`).
6. Async trigger/state transition validation (kept in integration tests for job lifecycle semantics).

## Related functional reliability evidence (async + mutate flows)

Use existing tests as companions for write/queue heavy flows that are not pure `GET` load probes:

```bash
./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/api/test_exports_foundation_api.py
./scripts/pytest.sh tests/test_package_pipeline.py tests/test_documents_generate.py
./scripts/pytest.sh tests/integration/test_pipeline_steps_happy_path.py tests/integration/test_pipeline_idempotency.py
```

## Notes

- Prefer running against PostgreSQL-backed local/stage environments for representative numbers.
- Capture command output into artifacts for pilot/release evidence.
- If p95 or error-rate degrades, pair the probe with SQL echo / query plans to review N+1 and index gaps.
