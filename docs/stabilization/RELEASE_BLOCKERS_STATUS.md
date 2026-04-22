# RELEASE_BLOCKERS_STATUS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing`

Этот документ — **канонический source of truth** для статусов release-blocker-ов.

Cross-links:
- `RELEASE_READINESS.md`
- `GAP_REPORT.md`
- `docs/stabilization/PLAN.md`
- `ACCEPTANCE_TEST_MATRIX.md`

## Blockers table (canonical)

| id | area | status(done/partial/missing) | owner | evidence_command_or_workflow | artifact_path | last_verified_utc |
|---|---|---|---|---|---|---|
| RB-001 | Restore drill acceptance closure | partial | SRE / Platform | `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill` or `.github/workflows/restore-drill.yml` | `artifacts/restore-drill/latest-postgres-minio.json` | 2026-04-22T00:00:00Z |
| RB-002 | Performance baseline release evidence | partial | Platform / QA | `.github/workflows/perf-baseline.yml` (`baseline`) | `artifacts/perf/nightly/trend-manifest.json` | 2026-04-22T00:00:00Z |
| RB-003 | Final acceptance overall pass | partial | QA / Platform | `make final-acceptance` (wrapper: `scripts/final_acceptance.sh`) | `artifacts/final_acceptance/summary.json` | 2026-04-22T00:00:00Z |
| RB-004 | Security gate ownership + escalation SLA codification | missing | Platform / Security | `.github/workflows/ci.yml` + static gates checks in `scripts/ci/static_gates.sh` after ownership codification | `docs/stabilization/security-gates.md` and `.github/CODEOWNERS` | 2026-04-22T00:00:00Z |
| RB-005 | Secrets-dependent e2e diagnostics hardening | missing | QA Automation | `.github/workflows/e2e-smoke.yml` with `tests/e2e/access/test_access_enforcement_matrix.py` diagnostics closure | `artifacts/e2e/access-enforcement/*.log` | 2026-04-22T00:00:00Z |
| RB-006 | Coverage non-regression gate | done | QA / Backend | `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json` | `artifacts/coverage.json` | 2026-04-22T00:00:00Z |

## Binary Go/No-Go (artifact-bound, no manual meeting-review steps)

Все пункты ниже бинарные (`YES`/`NO`) и определяются только по артефактам.

| # | Binary criterion | Current | Verification command/workflow | Required artifact |
|---|---|---|---|---|
| 1 | Restore drill latest artifact confirms acceptance (`success=true`, verification booleans true) | NO | `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill` or `.github/workflows/restore-drill.yml` | `artifacts/restore-drill/latest-postgres-minio.json` |
| 2 | Perf baseline manifest for current release window is present and complete | NO | `.github/workflows/perf-baseline.yml` | `artifacts/perf/nightly/trend-manifest.json` |
| 3 | Final acceptance summary reports `overall_status=pass` | NO | `make final-acceptance` | `artifacts/final_acceptance/summary.json` |
| 4 | Security ownership escalation policy is codified in versioned docs + ownership map | NO | `.github/workflows/ci.yml` (docs/static gates) | `docs/stabilization/security-gates.md` and `.github/CODEOWNERS` |
| 5 | Secrets-dependent e2e diagnostics artifact exists and is green | NO | `.github/workflows/e2e-smoke.yml` | `artifacts/e2e/access-enforcement/*.log` |
| 6 | Coverage baseline check is green | YES | `.github/workflows/ci.yml` + `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json` | `artifacts/coverage.json` |
| 7 | All blocker rows in this file are `done` | NO | `python - <<'PY'\nfrom pathlib import Path\ntext = Path('docs/stabilization/RELEASE_BLOCKERS_STATUS.md').read_text(encoding='utf-8')\nrows = [line for line in text.splitlines() if line.startswith('| RB-')]\nstatuses = [r.split('|')[3].strip() for r in rows]\nassert statuses and all(s == 'done' for s in statuses), statuses\nprint('all blockers done')\nPY` | `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` |

## Release verdict coupling

- Итоговый release verdict в `RELEASE_READINESS.md` обязан ссылаться на этот файл.
- Любое изменение blocker-статуса сначала вносится сюда, затем синхронизируется в связанные документы.
