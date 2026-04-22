# Stabilization Plan Tracker (Canonical)

- **Updated on:** 2026-04-22
- **Owner:** Stabilization Program (Platform + QA + SRE)
- **Canonical status vocabulary:** `done` / `partial` / `missing`

This tracker is aligned with `ACCEPTANCE_TEST_MATRIX.md`, `GAP_REPORT.md`, and `RELEASE_READINESS.md`.

## Block A — CI/CD stabilization gates

### A.1 Canonical security gate matrix
- **status:** `partial`
- **owner:** Platform / DevEx
- **evidence paths:** `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`, `scripts/ci/static_gates.sh`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_default_secrets.py`, `docs/stabilization/security-gates.md`

### A.2 Gate ownership and escalation SLA codification
- **status:** `missing`
- **owner:** Platform / Security
- **evidence paths:** `docs/stabilization/security-gates.md`, `.github/workflows/ci.yml`, `.github/CODEOWNERS` (if introduced)

## Block B — Test coverage visibility

### B.1 Critical-path coverage matrix normalization
- **status:** `partial`
- **owner:** QA / Backend / Frontend
- **evidence paths:** `docs/stabilization/coverage.md`, `tests/integration/test_tenant_isolation.py`, `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/e2e/final_regression/test_final_regression_api.py`, `frontend/e2e/smoke.spec.ts`, `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`

### B.2 Secrets-dependent e2e signal hardening
- **status:** `missing`
- **owner:** QA Automation
- **evidence paths:** `.github/workflows/e2e-smoke.yml`, `frontend/e2e/smoke.spec.ts`, `tests/e2e/access/test_access_enforcement_matrix.py`, `docs/stabilization/e2e-access.md`

## Block C — Backup/restore operational drill

### C.1 Repeatable restore drill with evidence bundle
- **status:** `partial`
- **owner:** SRE / Platform
- **evidence paths:** `scripts/restore_drill.py`, `backend/app/cli/main.py`, `tests/test_cli_commands.py`, `tests/test_health_ready.py`, `tests/integration/test_tenant_isolation.py`, `docs/runbooks/RESTORE_TENANT.md`, `docs/stabilization/restore-drill.md`

### C.2 Rollback window and go/no-go criteria formalization
- **status:** `missing`
- **owner:** SRE / Incident Commander
- **evidence paths:** `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md`, `scripts/restore_drill.py`, `tests/test_health_ready.py`

## Cross-block evidence index

| Block | tests | workflows | scripts | docs |
|---|---|---|---|---|
| A | `tests/test_api_guardrails.py`, `tests/test_openapi_contract.py` | `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` | `scripts/ci/static_gates.sh`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_default_secrets.py` | `docs/stabilization/security-gates.md` |
| B | `tests/integration/test_tenant_isolation.py`, `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/e2e/access/test_access_enforcement_matrix.py`, `frontend/e2e/smoke.spec.ts` | `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml` | `scripts/pytest.sh`, `scripts/smoke.sh` | `docs/stabilization/coverage.md`, `docs/stabilization/e2e-access.md`, `docs/TEST_BASELINE.md` |
| C | `tests/test_cli_commands.py`, `tests/test_health_ready.py`, `tests/integration/test_tenant_isolation.py` | `.github/workflows/ci.yml` | `scripts/restore_drill.py` | `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md` |

## Change-control rule

Any PR that changes block status must update:
1. `docs/stabilization/PLAN.md` status,
2. one corresponding domain doc,
3. one executable evidence path (test/workflow/script).
