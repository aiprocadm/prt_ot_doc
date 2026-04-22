# Stabilization Coverage Gates

- **Updated on (UTC):** 2026-04-22
- **Owner:** QA Automation + Backend
- **Canonical status vocabulary:** `done` / `partial` / `missing`

This document defines backend line + branch coverage policy used for CI non-regression gating.

## Coverage gate status

| Coverage claim | Status | Partial/missing reason | Exact command/workflow | Artifact path(s) | Evidence links |
|---|---|---|---|---|---|
| Coverage regression gate is enforced | `done` | — | `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`; workflow: `.github/workflows/ci.yml` (`backend-tests`). | `artifacts/coverage.json`, `artifacts/coverage.xml`, `artifacts/coverage-term-missing.txt`; CI artifact: `backend-test-report`. | `.github/workflows/ci.yml`, `scripts/ci/check_backend_coverage_baseline.py`, `docs/stabilization/backend_coverage_baseline.json` |
| Critical-path traceability across unit/integration/e2e is complete | `partial` | Cross-layer mapping exists but not all acceptance scenarios are fully `done` in matrix (notably performance and some workflow edges). | Supporting suites: `./scripts/pytest.sh tests/e2e/final_regression/test_final_regression_api.py` and frontend smoke in `.github/workflows/e2e-smoke.yml`. | CI artifacts split across backend + e2e runs; no single consolidated traceability artifact yet. | `ACCEPTANCE_TEST_MATRIX.md`, `docs/TESTING.md`, `.github/workflows/e2e-smoke.yml` |
| Secrets-dependent e2e reliability hardening is complete | `missing` | Secrets-dependent branch in e2e smoke remains a target state and is not closed as release-ready evidence. | Target workflow: `.github/workflows/e2e-smoke.yml` (`playwright-smoke-credential` with `repo_secrets`). | Missing closed evidence bundle for required secret-backed runs in release artifacts. | `docs/stabilization/e2e-access.md`, `GAP_REPORT.md` |

Release decision is governed by the **single go/no-go checklist** in `RELEASE_READINESS.md`.

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

- Plan tracker: `docs/stabilization/PLAN.md`
- Acceptance scenarios: `ACCEPTANCE_TEST_MATRIX.md`
- Gap log: `GAP_REPORT.md`
- Release verdict: `RELEASE_READINESS.md`
- Accepted constraints: `KNOWN_LIMITATIONS.md`
