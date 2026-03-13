# Known Limitations (Release Candidate)

## External integrations / infrastructure
1. **DB-dependent migration flow** requires configured and reachable Postgres endpoint for full green migration pipeline.
2. **External integrations** (S3/EDO/other stubs) are environment-sensitive; full resilience validation requires integrated environment.

## Backend
1. Global lint baseline includes extensive pre-existing Ruff issues; not fully remediated in this RC pass.
2. Full backend suite is large and contains legacy unstable areas outside critical-path fixes completed here.

## Frontend
1. Tests pass but emit significant `act(...)` warnings and React Router future warnings; this can hide real regressions in CI logs.
2. Bundle warning for large chunks remains in production build output.

## E2E / DevOps
1. End-to-end smoke across full stack (with dockerized dependencies and external services) still required before final release sign-off.
2. Environment parity (local vs CI vs production-like) must be validated for migration and background jobs.
