# FAILURE_MAP

## Audit run timestamp
- 2026-02-15

## Executed smoke checks
1. `make dev:lite`
2. `curl http://127.0.0.1:8000/health`
3. `curl http://127.0.0.1:8000/ready`
4. `pytest --collect-only`
5. `cd frontend && npm run test`

## Failures / warnings found

### P0 (blocking)
- **None** in this pass.

### P1 (important, non-blocking)
- `make dev:lite` cold start is slow because it always runs full pip install and `npm ci` before boot.
- SQLAlchemy relationship overlap warnings appear on startup (non-fatal) for `Workplace/Position/RiskHazard` relations.

### P2 (quality/noise)
- Frontend tests pass but emit React `act(...)` warnings in several suites.
- npm warns about deprecated transitive packages and `Unknown env config "http-proxy"`.

## Validation outcome
- API health endpoints return HTTP 200 in dockerless mode.
- Pytest discovery includes `tests/` and `integration_tests/`.
- Frontend vitest suite passes.
