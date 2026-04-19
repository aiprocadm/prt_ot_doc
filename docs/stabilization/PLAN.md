# Stabilization Plan Tracker (Canonical)

_Last updated: 2026-04-19._

This file is the canonical tracker for stabilization workstreams **A–G**. It is intentionally evidence-first: every status line must point to existing code, workflows, tests, or scripts in this repository.

## Global status legend

- **Green** — implemented and covered by code + automated checks.
- **Yellow** — partially implemented; coverage or operations evidence is incomplete.
- **Red** — no concrete implementation in repo yet.

## Workstream tracker

| Workstream | Scope | Status | Current-state evidence | Explicit gaps / blockers | Acceptance criteria |
|---|---|---|---|---|---|
| **A** | CI/CD stabilization gates | Yellow | `.github/workflows/ci.yml` runs lint/static, backend tests, contract tests, frontend checks, and smoke compose; static guards are implemented via `scripts/ci/static_gates.sh`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_default_secrets.py`. | No single stabilization gate document that maps each required control to a job and blocking policy in one place. | 1) `docs/stabilization/security-gates.md` maintained and mapped to exact CI jobs/scripts. 2) Every gate has pass/fail owner and evidence artifact path. |
| **B** | Test coverage visibility (unit/integration/e2e) | Yellow | Integration suites exist in `tests/integration/*`; e2e/API suites exist in `tests/e2e/*`; frontend smoke exists in `frontend/e2e/smoke.spec.ts`; CI runs `pytest` and frontend coverage gate in `.github/workflows/ci.yml`. | Coverage status is spread across legacy stabilization docs; no single tracker keyed by critical path. | 1) `docs/stabilization/coverage.md` maps critical paths to concrete tests. 2) Gaps are explicit and linked to missing test files/markers. |
| **C** | Backup/restore operational drill | Yellow | CLI entry points exist for backup/restore in `backend/app/cli/main.py`; restore runbook exists in `docs/runbooks/RESTORE_TENANT.md`; CLI behavior has baseline tests in `tests/test_cli_commands.py`. | No end-to-end restore drill checklist with required evidence artifacts (timestamps, validation commands, rollback window). | 1) `docs/stabilization/restore-drill.md` defines repeatable drill and evidence package. 2) Drill references executable commands/scripts only. |
| **D** | Performance baseline and regression budget | Yellow | Load probe and run guidance exist in `scripts/perf/api_load.py` and `scripts/perf/README.md`; job/status and pipeline reliability tests exist (`tests/integration/test_job_status_flow.py`, `tests/integration/test_pipeline_steps_happy_path.py`). | No committed baseline dataset (p50/p95/error%) per endpoint/profile and no CI perf regression threshold. | 1) `docs/stabilization/perf-baseline.md` records measured baseline table + command lines. 2) Any target without measurement is marked as gap. |
| **E** | Security controls and enforcement gates | Yellow | Tenant/RBAC-ABAC controls exist in `backend/app/modules/rbac_abac/*`, tenant checks in API modules such as `backend/app/modules/files/api.py`; security tests exist (`tests/test_rbac_abac.py`, `tests/test_tenant_security.py`, `tests/integration/test_abac_query_isolation.py`). | Security gating is distributed; no canonical “required before merge” list tied to workflows and test modules. | 1) `docs/stabilization/security-gates.md` defines required gates and evidence location. 2) `docs/stabilization/rbac-matrix.md` defines endpoint vs role/access evidence. |
| **F** | E2E access and role-path reliability | Yellow | Browser e2e smoke scenarios are in `frontend/e2e/smoke.spec.ts`; scheduled/manual e2e workflow exists in `.github/workflows/e2e-smoke.yml`; backend e2e/pilot API checks exist in `tests/e2e/pilot_smoke/test_pilot_smoke_matrix.py`. | Current e2e requires optional secrets; absent credentials skip critical login/role tests, reducing signal quality. | 1) `docs/stabilization/e2e-access.md` defines required credential matrix and skip policy. 2) Required scenarios (login, limited-role denial, logout, protected-route redirect) mapped to tests. |
| **G** | File pipeline hardening (upload, storage, AV, tenancy) | Yellow | File module has upload/init/finalize/download endpoints in `backend/app/modules/files/api.py`, service logic in `backend/app/modules/files/service.py`, key-safety in `backend/app/modules/files/storage.py`, AV scan stub in `backend/app/modules/files/av.py`; tests include `tests/test_files_upload.py`, `tests/test_file_storage.py`, `tests/services/test_file_storage_service.py`, `tests/test_files_core_next54.py`. | No single hardening checklist that ties threats to controls and specific tests; AV implementation is currently simulated/stubbed in module-level scanner. | 1) `docs/stabilization/file-hardening.md` maps threat → control → evidence test/path. 2) Known residual risks and compensating controls are explicit. |

## Assumptions (current)

1. Stabilization scope is repository-internal and verified by existing CI/e2e pipelines only (`.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`).
2. Tenant isolation remains a non-negotiable invariant across API, jobs, and file operations (see `tests/integration/test_tenant_isolation.py`, `tests/integration/test_cross_tenant_resource_matrix.py`).
3. “Done” requires executable evidence (tests, scripts, workflow jobs), not prose-only updates.

## Cross-workstream blockers

- **Secrets-dependent e2e signal**: role/login scenarios in `frontend/e2e/smoke.spec.ts` are skipped when `E2E_*` vars are missing; scheduled workflow currently tolerates skipped tests.
- **Restore drill evidence format not standardized**: runbook exists but drill artifact requirements are not codified (`docs/runbooks/RESTORE_TENANT.md`).
- **Perf baseline not versioned as measured outputs**: probe tooling exists (`scripts/perf/api_load.py`) but baseline numbers are not yet tracked in repo.

## Change-control rule for this tracker

Any stabilization PR that changes status in workstreams A–G must also update:

- this `PLAN.md` row status,
- one domain file (`coverage.md`, `restore-drill.md`, `perf-baseline.md`, `security-gates.md`, `rbac-matrix.md`, `e2e-access.md`, or `file-hardening.md`),
- and at least one evidence link to code/tests/workflow paths changed in that PR.
