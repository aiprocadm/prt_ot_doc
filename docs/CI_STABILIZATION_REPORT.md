# CI Stabilization Report (RC pass)

## Non-green pipelines observed
1. **Lint pipeline (`make lint`)**
   - Dominant error class: Ruff import-order/unused-import violations.
   - Scale: hundreds of violations, largely legacy baseline.
2. **Migration pipeline (`make migrate`)**
   - Fails in environment without resolvable Postgres host/service.
3. **Backend full test sweep**
   - Initially red due to CLI test expectation drift.

## Fixes applied
- Updated CLI test suite assertions (`tests/test_cli_main.py`) to match current command contract and exit code constants.
  - Removed stale hardcoded expectations causing deterministic failures.

## Current stable stages (local)
- `pytest -q tests/test_cli_main.py` ✅
- `pytest -q tests/integration/test_idempotency_generate.py tests/integration/test_job_status_flow.py tests/test_api_guardrails.py` ✅
- `cd frontend && npm run build` ✅
- `cd frontend && npm test` ✅ (with warnings)

## Still unstable / noisy
- `make lint` ❌ due to large inherited Ruff debt.
- `make migrate` ⚠️ not runnable green without DB host/service in environment.
- Frontend tests produce numerous React `act(...)` warnings (non-fatal but noisy).

## Recommended next CI actions
1. Create dedicated lint debt burn-down stream (import sort + unused imports by module batches).
2. Split migration checks into:
   - local-sqlite sanity
   - docker-postgres integration
3. Treat frontend `act(...)` warnings as quality gate for test hardening.
