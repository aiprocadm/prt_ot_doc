# RELEASE_BLOCKERS_STATUS

- **Updated on (UTC):** 2026-04-22
- **Owner:** Release Manager + Platform + QA + SRE
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Single source of truth for release-critical statuses and evidence links.**

**Authoring order:** update this file first, then sync [`RELEASE_READINESS.md`](../../RELEASE_READINESS.md) (verdict + RC summary). See **“How to update the release verdict”** in `RELEASE_READINESS.md`.

Cross-links:
- `RELEASE_READINESS.md`
- `ACCEPTANCE_TEST_MATRIX.md`
- `KNOWN_LIMITATIONS.md`
- `GAP_REPORT.md`
- `docs/stabilization/PLAN.md`

## Unified release-critical criteria matrix

| Criterion ID | Source doc | Criterion (release-critical) | Unified status | Evidence (test/workflow/artifact/doc section) |
|---|---|---|---|---|
| RC-001 | `RELEASE_READINESS.md` | Restore drill acceptance criteria pass in latest run | `partial` | Workflow: `.github/workflows/restore-drill.yml`; command: `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill`; artifact: `artifacts/restore-drill/latest-postgres-minio.json`; doc: `docs/stabilization/restore-drill.md` |
| RC-002 | `RELEASE_READINESS.md` | Perf baseline manifest is published for release window | `partial` | Workflow: `.github/workflows/perf-baseline.yml`; artifact: `artifacts/perf/nightly/trend-manifest.json`; doc: `scripts/perf/README.md` |
| RC-003 | `RELEASE_READINESS.md` | Coverage non-regression gate is green vs baseline | `done` | Workflow: `.github/workflows/ci.yml` (`backend-tests`); command: `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`; artifact: `artifacts/coverage.json`; doc: `docs/stabilization/coverage.md` |
| RC-004 | `RELEASE_READINESS.md` + `ACCEPTANCE_TEST_MATRIX.md` | Final acceptance bundle is fully passing (`overall_status=pass`) | `partial` | Command: `make final-acceptance` (`scripts/final_acceptance.sh`); workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; artifact: `artifacts/final_acceptance/summary.json` |
| RC-005 | `RELEASE_READINESS.md` + `PLAN.md` | Security gate ownership + escalation SLA codified | `blocked` | Workflow target: `.github/workflows/ci.yml`; script: `scripts/ci/static_gates.sh`; doc target: `docs/stabilization/security-gates.md`; ownership map target: `.github/CODEOWNERS` |
| RC-006 | `RELEASE_READINESS.md` + `PLAN.md` | Secrets-dependent e2e diagnostics produce stable green artifact | `missing` | Workflow target: `.github/workflows/e2e-smoke.yml`; test target: `tests/e2e/access/test_access_enforcement_matrix.py`; artifact target: `artifacts/e2e/access-enforcement/*.log`; doc: `docs/stabilization/e2e-access.md` |
| RC-007 | `ACCEPTANCE_TEST_MATRIX.md` | Replace dry-run/reporting E2E acceptance path | `partial` | Workflow: `.github/workflows/ci.yml`; evidence currently partial in `artifacts/final_acceptance/*.log`; doc: section “Matrix (deduplicated canonical table)” |
| RC-008 | `ACCEPTANCE_TEST_MATRIX.md` | PDF conversion reliability acceptance path | `partial` | Workflow: `.github/workflows/ci.yml`; evidence currently partial in `artifacts/final_acceptance/*.log`; doc: section “Matrix (deduplicated canonical table)” |
| RC-009 | `ACCEPTANCE_TEST_MATRIX.md` | Approval/sign/archive handoff acceptance path | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; evidence currently partial in `artifacts/final_acceptance/*.log` |
| RC-010 | `ACCEPTANCE_TEST_MATRIX.md` | Workspace hub routes full acceptance behavior | `partial` | Workflow: `.github/workflows/e2e-smoke.yml`; script: `npm --prefix frontend run build`; doc evidence: workspace route pages listed in matrix |
| RC-011 | `KNOWN_LIMITATIONS.md` | Notifications escalation/provider orchestration completeness | `missing` | Tests: `tests/api/test_notifications_calendar_api.py`, `tests/test_workflow_api.py`; workflow: `.github/workflows/ci.yml`; doc: `GAP_REPORT.md` |
| RC-012 | `GAP_REPORT.md` | Restore drill formal RTO/RPO go/no-go criteria | `missing` | Script target: `scripts/restore_drill.py`; test target: `tests/test_health_ready.py`; docs: `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md` |
| RC-013 | `GAP_REPORT.md` | Scope model migration to relational/indexed model | `missing` | Workflow target: `.github/workflows/ci.yml`; evidence targets in migration tests/scripts; doc target: schema/migration design docs |
| RC-014 | `GAP_REPORT.md` | Dedicated branch entity (separate from `Site`) | `missing` | Workflow target: `.github/workflows/ci.yml`; evidence targets in contract tests + migration scripts |
| RC-015 | `PLAN.md` | Canonical security gate matrix operational closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; scripts: `scripts/ci/static_gates.sh`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_default_secrets.py`; doc: `docs/stabilization/security-gates.md` |
| RC-016 | `PLAN.md` | Critical-path coverage matrix normalization closure | `partial` | Workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; tests listed in Block B.1 of `docs/stabilization/PLAN.md`; docs: `docs/stabilization/coverage.md`, `ACCEPTANCE_TEST_MATRIX.md` |

## Release blockers checklist (artifact/workflow mapped)

Each checklist item maps to a concrete workflow/job/artifact and to one or more criteria above.

- [ ] **RB-001 Restore drill closure** (`RC-001`, `RC-012`)
  - Workflow/job: `.github/workflows/restore-drill.yml` / `restore-drill`
  - Artifact: `artifacts/restore-drill/latest-postgres-minio.json` (or uploaded `restore-drill-evidence`)
  - Pass condition: latest artifact confirms acceptance booleans + smoke success.

- [ ] **RB-002 Perf baseline closure** (`RC-002`)
  - Workflow/job: `.github/workflows/perf-baseline.yml` / `baseline`
  - Artifact: `artifacts/perf/nightly/trend-manifest.json`, `artifacts/perf/nightly/summary.md`
  - Pass condition: release-window baseline manifest and summary are present and complete.

- [ ] **RB-003 Final acceptance closure** (`RC-004`, `RC-007`, `RC-008`, `RC-009`, `RC-010`)
  - Workflow/job: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`
  - Artifact: `artifacts/final_acceptance/summary.json`
  - Pass condition: `overall_status=pass`; no required acceptance scenario remains `partial/missing`.

- [ ] **RB-004 Security ownership & escalation closure** (`RC-005`, `RC-015`)
  - Workflow/job: `.github/workflows/ci.yml` (docs/static gates checks)
  - Artifact/doc: `docs/stabilization/security-gates.md` and `.github/CODEOWNERS`
  - Pass condition: ownership fallback + escalation SLA are codified and versioned.

- [ ] **RB-005 Secrets-dependent e2e diagnostics closure** (`RC-006`)
  - Workflow/job: `.github/workflows/e2e-smoke.yml`
  - Artifact: `artifacts/e2e/access-enforcement/*.log`
  - Pass condition: diagnostics artifact exists and is green for required environments.

- [x] **RB-006 Coverage non-regression closure** (`RC-003`, `RC-016`)
  - Workflow/job: `.github/workflows/ci.yml` / `backend-tests`
  - Artifact: `artifacts/coverage.json` (+ `backend-test-report` upload)
  - Pass condition: baseline check passes via `scripts/ci/check_backend_coverage_baseline.py`.

## Binary Go/No-Go

Release may be marked **READY** only when all checklist items RB-001..RB-006 are checked.

## Synchronization rule

Any release-critical status update must be done in this file first, then synchronized to:
1. `RELEASE_READINESS.md`
2. `ACCEPTANCE_TEST_MATRIX.md`
3. `KNOWN_LIMITATIONS.md`
4. `GAP_REPORT.md`
5. `docs/stabilization/PLAN.md`
