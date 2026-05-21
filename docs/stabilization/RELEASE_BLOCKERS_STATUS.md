# RELEASE_BLOCKERS_STATUS

- **Updated on (UTC):** 2026-05-21
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

## Recent stabilization activity (post-billing-restore, 2026-05-21)

GitHub Actions billing was restored on 2026-05-21 after a ~9-week block (from 2026-03-21). The first CI runs surfaced multiple layers of latent rot. Eight iterations of fixes have been merged to `main` over the day:

| PR | Iteration | Scope |
|---|---|---|
| [#549](https://github.com/aiprocadm/prt_ot_doc/pull/549) | iter-1 | Initial workflow plumbing: image tag, readiness wait, first attempt at matrix-in-if fix |
| [#550](https://github.com/aiprocadm/prt_ot_doc/pull/550) | iter-2 | bitnamilegacy minio, `resolve-credential-matrix` job pattern, 6 ci.yml fixes (trivy v0.36.0, gitleaks GITHUB_TOKEN, bandit dep, static_gates.sh backslash, templateversionstatus 'ACTIVE' enum) |
| [#551](https://github.com/aiprocadm/prt_ot_doc/pull/551) | iter-3..4 | Missing regulatory_inspection migration, gitleaks `--no-git`, enum `create_type=False`, fetch-depth, frontend axios/react-router CVE upgrades |
| [#552](https://github.com/aiprocadm/prt_ot_doc/pull/552) | iter-5 | 6 CI failures: enum revert + async tests + import paths + sbom dir + base image patches |
| [#553](https://github.com/aiprocadm/prt_ot_doc/pull/553) | iter-6 | 5 CI failures after PR #552 merge |
| [#554](https://github.com/aiprocadm/prt_ot_doc/pull/554) | iter-7 | 2 regressions introduced by iter-6 |
| [#555](https://github.com/aiprocadm/prt_ot_doc/pull/555) | iter-8 | 3 main CI jobs + 3 post-billing app defects (RB-001/002/005 paths); `postgresql.ENUM` fix extended to 7 migrations total |

**Post-iter-8 main CI state (as of 2026-05-21T15:17Z):** [run 26235153179](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26235153179) is in progress; **3 jobs already failed** — `perf-smoke`, `alembic-postgres-upgrade`, `container-image-scan`. Root cause for `alembic-postgres-upgrade` (pre-iter-8 log): `DuplicateObjectError: type "attestationstatus" already exists` — same class of bug iter-8 targeted, suggesting additional migrations may still need the same `postgresql.ENUM(create_type=False)` treatment (iter-9 candidate).

**RB-001/002/005 re-validation status:** the three release-blocker workflows (`restore-drill.yml`, `perf-baseline.yml`, `e2e-smoke.yml`) have **not yet been re-triggered against post-iter-8 main**. Most recent runs were on `fix/ci-workflows-billing-restore` (pre-iter-8) and almost all are `failure` except a single sqlite-mode restore-drill green ([run 26215954984](https://github.com/aiprocadm/prt_ot_doc/actions/runs/26215954984)). The blocker checkboxes therefore stay `[ ]` until fresh post-iter-8 green artifacts exist.

## Unified release-critical criteria matrix

| Criterion ID | Source doc | Criterion (release-critical) | Unified status | Evidence (test/workflow/artifact/doc section) |
|---|---|---|---|---|
| RC-001 | `RELEASE_READINESS.md` | Restore drill acceptance criteria pass in latest run | `partial` | Workflow: `.github/workflows/restore-drill.yml`; command: `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill`; artifact: `artifacts/restore-drill/latest-postgres-minio.json`; doc: `docs/stabilization/restore-drill.md` |
| RC-002 | `RELEASE_READINESS.md` | Perf baseline manifest is published for release window | `partial` | Workflow: `.github/workflows/perf-baseline.yml`; artifact: `artifacts/perf/nightly/trend-manifest.json`; doc: `scripts/perf/README.md` |
| RC-003 | `RELEASE_READINESS.md` | Coverage non-regression gate is green vs baseline | `done` | Workflow: `.github/workflows/ci.yml` (`backend-tests`); command: `python scripts/ci/check_backend_coverage_baseline.py --coverage-json artifacts/coverage.json --baseline docs/stabilization/backend_coverage_baseline.json`; artifact: `artifacts/coverage.json`; doc: `docs/stabilization/coverage.md` |
| RC-004 | `RELEASE_READINESS.md` + `ACCEPTANCE_TEST_MATRIX.md` | Final acceptance bundle is fully passing (`overall_status=pass`) | `partial` | Command: `make final-acceptance` (`scripts/final_acceptance.sh`); workflows: `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`; artifact: `artifacts/final_acceptance/summary.json` |
| RC-005 | `RELEASE_READINESS.md` + `PLAN.md` | Security gate ownership + escalation SLA codified | `done` | Workflow target: `.github/workflows/ci.yml`; script: `scripts/ci/static_gates.sh`; doc target: `docs/stabilization/security-gates.md` (escalation policy §"Escalation policy"); ownership map: `.github/CODEOWNERS` (5 teams mapped as of 2026-04-30) |
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

- [x] **RB-004 Security ownership & escalation closure** (`RC-005`, `RC-015`)
  - Workflow/job: `.github/workflows/ci.yml` (docs/static gates checks)
  - Artifact/doc: `docs/stabilization/security-gates.md` and `.github/CODEOWNERS`
  - Pass condition: ownership fallback + escalation SLA are codified and versioned.
  - **Status: DONE** (2026-04-30)
    - ✅ Ownership domains: auth, rbac/abac, files, migrations, workflows (`.github/CODEOWNERS`)
    - ✅ Escalation policy: T+0, T+4h, T+1d, break-glass (documented in `security-gates.md` §"Escalation policy")
    - ✅ Team mappings: 5 reviewer groups aligned (`reviewers-auth`, `reviewers-rbac-abac`, `reviewers-files`, `reviewers-data-platform`, `reviewers-platform-infra`)

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

**Current status:** 3/6 blockers closed (RB-003 partial, RB-004 done, RB-006 done).
**Remaining:** RB-001 (restore drill), RB-002 (perf baseline), RB-005 (e2e diagnostics).

## Synchronization rule

Any release-critical status update must be done in this file first, then synchronized to:
1. `RELEASE_READINESS.md`
2. `ACCEPTANCE_TEST_MATRIX.md`
3. `KNOWN_LIMITATIONS.md`
4. `GAP_REPORT.md`
5. `docs/stabilization/PLAN.md`
