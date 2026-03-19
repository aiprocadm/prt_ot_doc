# Perf / load foundations (release candidate)

These probes are intentionally lightweight and reproducible in a pilot or staging stand. They are not a substitute for a full performance lab, but they give a stable baseline for hot-path review and async reliability checks.

## API read / registry smoke
```bash
python scripts/perf/api_load.py --base-url http://localhost:8000 --path /health --requests 100 --concurrency 20
python scripts/perf/api_load.py --base-url http://localhost:8000 --path /api/v1/templates --tenant demo --requests 100 --concurrency 20
```

## Search smoke
```bash
python scripts/perf/api_load.py --base-url http://localhost:8000 --path '/api/v1/search/suggest?q=doc' --tenant demo --requests 50 --concurrency 10
```

## Export / document-generation readiness
Use existing async regression suites together with the smoke probe to validate that queue-backed jobs expose visible status transitions instead of silent hangs.

```bash
./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/api/test_exports_foundation_api.py
./scripts/pytest.sh tests/test_package_pipeline.py tests/test_documents_generate.py
```

## Bulk import / tenant bootstrap
```bash
./scripts/pytest.sh tests/e2e/pilot_smoke/test_pilot_smoke_matrix.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_idempotency_generate.py
```

## Worker / retry visibility
```bash
./scripts/pytest.sh tests/test_outbox_dispatch.py tests/test_webhooks_dispatch.py tests/integration/test_job_status_flow.py
```

## Notes
- Prefer running against PostgreSQL-backed local/stage environments for representative numbers.
- Capture command output into artifacts for pilot/release evidence.
- If p95 or error-rate degrades, pair the probe with SQL echo / query plans to review N+1 and index gaps.
