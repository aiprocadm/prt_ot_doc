# Stabilization Coverage Gates

_Last updated: 2026-04-19._

This document defines the **backend line + branch coverage policy** used for CI non-regression gating.

## What is enforced in CI

The `backend-tests` job in `.github/workflows/ci.yml` now:

1. Runs `pytest` with branch + line coverage enabled.
2. Exports coverage outputs:
   - `artifacts/coverage.xml`
   - `artifacts/coverage.json`
   - `artifacts/coverage-term-missing.txt`
3. Runs `scripts/ci/check_backend_coverage_baseline.py` to fail the build if coverage regresses below the committed baseline.

## Baseline source and rationale

Baseline thresholds are committed in `docs/stabilization/backend_coverage_baseline.json`.

- Baseline date: **2026-04-19**.
- Basis: measured stabilization-focused backend suites covering critical services (auth, RBAC/ABAC, tenancy, files, jobs/outbox).
- Guard-band: thresholds are set slightly below measured values to avoid noise-driven flakes while still preventing downward drift.

### Current enforced thresholds

| Scope | Line % (min) | Branch % (min) | Why this scope exists |
|---|---:|---:|---|
| overall backend/app | 47.0 | 36.0 | Prevents broad accidental test erosion. |
| auth | 65.5 | 49.4 | Login/authz regressions are high impact. |
| rbac_abac | 66.2 | 46.3 | Permission regression risk is security-critical. |
| tenancy | 72.2 | 57.8 | Tenant isolation is a hard requirement. |
| files | 55.7 | 39.6 | Upload/storage hardening is reliability + security critical. |
| jobs_outbox | 31.9 | 31.5 | Job/state + outbox delivery must not regress. |

## Ratchet policy (non-regression + gradual increase)

- **No-regression rule**: CI fails when any enforced threshold drops below baseline.
- **Ratchet rule**: when sustained coverage increases are observed (e.g., in 2+ consecutive green PRs), raise the corresponding baseline in `docs/stabilization/backend_coverage_baseline.json`.
- **Adjustment rule**: threshold reductions require explicit justification in PR notes and this document (for example, deliberate code deletion/move effects).

## Deterministic PR gate script

Use locally or in CI:

```bash
python scripts/ci/check_backend_coverage_baseline.py \
  --coverage-json artifacts/coverage.json \
  --baseline docs/stabilization/backend_coverage_baseline.json
```

The script compares:

- overall line + branch coverage, and
- per-module/service aggregates by path patterns

against the committed baseline and exits non-zero on regressions.


## Cross-reference: testing and acceptance

- Canonical testing strategy and CI map: `docs/TESTING.md`.
- Acceptance scenario matrix: `ACCEPTANCE_TEST_MATRIX.md`.

### Merge blocking behavior

Coverage is a **hard merge gate** via CI job `backend-tests`:
- if `pytest` coverage collection fails, job fails;
- if `check_backend_coverage_baseline.py` detects regression against `docs/stabilization/backend_coverage_baseline.json`, job fails;
- any failure in `backend-tests` blocks merge until fixed.
