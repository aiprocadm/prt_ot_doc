# Stabilization Coverage Gates

- **Updated on:** 2026-04-22
- **Owner:** QA Automation + Backend
- **Canonical status vocabulary:** `done` / `partial` / `missing`

This document defines backend line + branch coverage policy used for CI non-regression gating.

## Coverage gate status

- **Backend coverage baseline gate:** `done`
  - Evidence: `.github/workflows/ci.yml` (`backend-tests`), `scripts/ci/check_backend_coverage_baseline.py`, `docs/stabilization/backend_coverage_baseline.json`.
- **Critical-path traceability across unit/integration/e2e:** `partial`
  - Evidence: `ACCEPTANCE_TEST_MATRIX.md`, `docs/TESTING.md`, `.github/workflows/e2e-smoke.yml`.
- **Secrets-dependent e2e reliability hardening:** `missing`
  - Evidence target: `docs/stabilization/e2e-access.md`, `.github/workflows/e2e-smoke.yml`.

## What is enforced in CI

The `backend-tests` job in `.github/workflows/ci.yml`:
1. Runs `pytest` with line + branch coverage.
2. Exports `artifacts/coverage.xml`, `artifacts/coverage.json`, `artifacts/coverage-term-missing.txt`.
3. Runs `scripts/ci/check_backend_coverage_baseline.py` and fails on regression.

## Baseline source

Baseline thresholds are committed in `docs/stabilization/backend_coverage_baseline.json` (baseline date: 2026-04-19).

| Scope | Line % (min) | Branch % (min) |
|---|---:|---:|
| overall backend/app | 47.0 | 36.0 |
| auth | 65.5 | 49.4 |
| rbac_abac | 66.2 | 46.3 |
| tenancy | 72.2 | 57.8 |
| files | 55.7 | 39.6 |
| jobs_outbox | 31.9 | 31.5 |

## Deterministic local/CI check

```bash
python scripts/ci/check_backend_coverage_baseline.py \
  --coverage-json artifacts/coverage.json \
  --baseline docs/stabilization/backend_coverage_baseline.json
```

## Cross-links

- Testing strategy: `docs/TESTING.md`
- Acceptance scenarios: `ACCEPTANCE_TEST_MATRIX.md`
- Gap log: `GAP_REPORT.md`
- Release decision: `RELEASE_READINESS.md`
