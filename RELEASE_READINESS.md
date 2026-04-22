# RELEASE_READINESS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing`

## Evidence-backed readiness summary

| Readiness claim | Status | Partial/missing reason | Exact command/workflow | Artifact path(s) | Evidence links |
|---|---|---|---|---|---|
| Restore drill gate is executable and archived | `partial` | Go/no-go closure is not complete because latest linked evidence does not yet demonstrate all acceptance criteria in `docs/stabilization/restore-drill.md`. | Local/CI command: `python scripts/restore_drill.py --mode sqlite --output-dir artifacts/restore-drill` and `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill`; workflow: `.github/workflows/restore-drill.yml` (`restore-drill` job). | `artifacts/restore-drill/latest-sqlite.json`, `artifacts/restore-drill/latest-postgres-minio.json`; CI artifact bundle: `restore-drill-evidence`. | `docs/stabilization/restore-drill.md`, `.github/workflows/restore-drill.yml`, `GAP_REPORT.md` |
| Performance baseline gate is executable and archived | `partial` | Baseline automation exists, but release sign-off evidence bundle is not attached as a closed release artifact in decision docs. | Workflow: `.github/workflows/perf-baseline.yml` (`baseline` job) runs nightly profile via `python scripts/perf/api_load.py ...` commands generated from `scripts/perf/scenarios.json`. | `artifacts/perf/nightly/*.json`, `artifacts/perf/nightly/trend-manifest.json`, `artifacts/perf/nightly/summary.md`; CI artifact bundle: `perf-baseline-<run_id>`. | `.github/workflows/perf-baseline.yml`, `scripts/perf/README.md`, `ACCEPTANCE_TEST_MATRIX.md` |
| Coverage regression gate is active | `done` | — | `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`; workflow: `.github/workflows/ci.yml` (`backend-tests`). | `artifacts/coverage.json`, `artifacts/coverage.xml`, `artifacts/coverage-term-missing.txt`; CI artifact bundle: `backend-test-report`. | `docs/stabilization/coverage.md`, `.github/workflows/ci.yml`, `docs/stabilization/backend_coverage_baseline.json` |
| Acceptance gate is executable and archived | `partial` | Several acceptance scenarios remain partial/missing in the matrix (replace/reporting, PDF conversion, approval/sign/archive, perf smoke, workspace routes). | `make final-acceptance` (wrapper around `scripts/final_acceptance.sh`); targeted suite commands listed in `ACCEPTANCE_TEST_MATRIX.md`; workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`. | `artifacts/final_acceptance/summary.json`, `artifacts/final_acceptance/summary.md`, `artifacts/final_acceptance/*.log`. | `ACCEPTANCE_TEST_MATRIX.md`, `scripts/final_acceptance.sh`, `docs/stabilization/PLAN.md` |
| Full production runbook closure (RTO/RPO + escalation ownership + secrets e2e diagnostics) is complete | `missing` | Escalation ownership SLA and secrets-dependent e2e diagnostics are still tracked as unresolved release-critical gaps. | Workflow targets exist in `.github/workflows/ci.yml` and `.github/workflows/e2e-smoke.yml`, but closure commands are not yet marked done in plan/gap trackers. | Missing closure evidence bundle in release artifact set. | `docs/stabilization/restore-drill.md`, `docs/stabilization/security-gates.md`, `docs/stabilization/e2e-access.md`, `GAP_REPORT.md` |

## Go/No-Go checklist (single release decision checklist)

All criteria are binary and must be **YES** to flip verdict to `READY`.

| # | Binary criterion | Current | Required evidence command/workflow | Required artifact path(s) |
|---|---|---|---|---|
| 1 | Restore drill acceptance criteria pass in latest run (`success=true`, verification booleans true, smoke exit 0). | **NO** | `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill`; or `.github/workflows/restore-drill.yml`. | `artifacts/restore-drill/latest-postgres-minio.json` (or uploaded `restore-drill-evidence`). |
| 2 | Perf nightly baseline completed and trend manifest published for release window. | **NO** | `.github/workflows/perf-baseline.yml` (`Run nightly baseline profile`). | `artifacts/perf/nightly/trend-manifest.json`, `artifacts/perf/nightly/summary.md` (or `perf-baseline-<run_id>` artifact). |
| 3 | Coverage regression gate passed at or above committed baseline. | **YES** | `.github/workflows/ci.yml` (`backend-tests`) + `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`. | `artifacts/coverage.json` and `backend-test-report` artifact. |
| 4 | Final acceptance bundle passed with no required-check failures. | **NO** | `make final-acceptance` (or equivalent `./scripts/final_acceptance.sh`). | `artifacts/final_acceptance/summary.json` with `overall_status=pass`. |
| 5 | Plan/gap trackers have no release-critical `missing` entries. | **NO** | Document review workflow in release review meeting (no substitute automation yet). | Updated `docs/stabilization/PLAN.md` + `GAP_REPORT.md` showing no release-critical `missing`. |

## Launch readiness verdict

- **Verdict date (UTC):** 2026-04-22
- **Verdict:** **NOT READY**
- **Why still NOT READY:** checklist criteria #1, #2, #4, and #5 are currently **NO**, and unresolved release-critical gaps remain open.
