# Stabilization Plan Tracker (Canonical)

- **Updated on (UTC):** 2026-04-22
- **Owner:** Stabilization Program (Platform + QA + SRE)
- **Canonical status vocabulary:** `done` / `partial` / `missing` / `blocked`
- **Canonical blocker/status source:** `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`

This plan tracks execution ownership and evidence paths.
Release-critical status values are mirrored from `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` by Criterion ID.

## Block A — CI/CD stabilization gates

### A.1 Canonical security gate matrix (`RC-015`)
- **status:** `partial`
- **owner:** Platform / DevEx
- **evidence:**
  - **workflow:** `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`
  - **script:** `scripts/ci/static_gates.sh`, `scripts/ci/check_scoped_queries.py`, `scripts/ci/check_runtime_artifacts.py`, `scripts/ci/check_default_secrets.py`
  - **doc:** `docs/stabilization/security-gates.md`

### A.2 Gate ownership and escalation SLA codification (`RC-005`)
- **status:** `blocked`
- **owner:** Platform / Security
- **blocker detail:** ownership map approval/versioning is not yet finalized.
- **evidence target:**
  - **workflow:** `.github/workflows/ci.yml`
  - **doc:** `docs/stabilization/security-gates.md`
  - **ownership:** `.github/CODEOWNERS`

## Block B — Test coverage visibility

### B.1 Critical-path coverage matrix normalization (`RC-016`)
- **status:** `partial`
- **owner:** QA / Backend / Frontend
- **evidence:**
  - **test:** `tests/integration/test_tenant_isolation.py`, `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/e2e/final_regression/test_final_regression_api.py`, `frontend/e2e/smoke.spec.ts`
  - **workflow:** `.github/workflows/ci.yml`, `.github/workflows/e2e-smoke.yml`
  - **doc:** `docs/stabilization/coverage.md`, `ACCEPTANCE_TEST_MATRIX.md`

### B.2 Secrets-dependent e2e signal hardening (`RC-006`)
- **status:** `missing`
- **owner:** QA Automation
- **evidence target:**
  - **workflow:** `.github/workflows/e2e-smoke.yml`
  - **test:** `tests/e2e/access/test_access_enforcement_matrix.py`, `frontend/e2e/smoke.spec.ts`
  - **doc:** `docs/stabilization/e2e-access.md`

## Block C — Backup/restore operational drill

### C.1 Repeatable restore drill with evidence bundle (`RC-001`)
- **status:** `partial`
- **owner:** SRE / Platform
- **evidence:**
  - **script:** `scripts/restore_drill.py`
  - **workflow:** `.github/workflows/restore-drill.yml`
  - **artifact:** `artifacts/restore-drill/latest-postgres-minio.json`
  - **doc:** `docs/runbooks/RESTORE_TENANT.md`, `docs/stabilization/restore-drill.md`

### C.2 Rollback window and go/no-go criteria formalization (`RC-012`)
- **status:** `missing`
- **owner:** SRE / Incident Commander
- **evidence target:**
  - **doc:** `docs/stabilization/restore-drill.md`, `docs/runbooks/RESTORE_TENANT.md`
  - **script:** `scripts/restore_drill.py`
  - **test:** `tests/test_health_ready.py`

## Cross-links

- Canonical criteria, unified statuses, blockers checklist: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
- Release verdict: `RELEASE_READINESS.md`
- Acceptance status map: `ACCEPTANCE_TEST_MATRIX.md`
- Gap tracker: `GAP_REPORT.md`
- Constraints/limitations: `KNOWN_LIMITATIONS.md`

## Change-control rule

Any PR that changes a release-critical status must update:
1. `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (first),
2. this plan item by Criterion ID,
3. one executable evidence path (test/workflow/script/artifact),
4. one cross-linking verdict doc (`RELEASE_READINESS.md` or `GAP_REPORT.md`).
