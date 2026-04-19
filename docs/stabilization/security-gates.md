# Security Gates (Stabilization)

_Last updated: 2026-04-19._

This document maps currently implemented security-related checks to concrete workflows, scripts, and tests.

## Gate inventory (current state)

| Gate | Where implemented | Enforced today | Evidence path | Explicit gap |
|---|---|---|---|---|
| Scoped query guard | CI workflow step | Yes (blocking in CI job) | `.github/workflows/ci.yml`, `scripts/ci/check_scoped_queries.py` | No consolidated exception handling policy in one doc. |
| Runtime/build artifact guard | CI workflow step | Yes (blocking in CI job) | `.github/workflows/ci.yml`, `scripts/ci/check_runtime_artifacts.py` | Gate intent/coverage by artifact class not documented centrally. |
| Default secret guard | CI workflow step | Yes (blocking in CI job) | `.github/workflows/ci.yml`, `scripts/ci/check_default_secrets.py` | Secret scanning scope outside configured patterns is not tracked here. |
| Static tenant guard checks | CI workflow step | Yes (blocking in CI job) | `.github/workflows/ci.yml`, `scripts/ci/static_gates.sh` | No dedicated report artifact for static gate findings trend. |
| Tenant mismatch/ABAC runtime tests | test suite | Yes (inside backend pytest run) | `tests/test_rbac_abac.py`, `tests/test_tenant_security.py`, `tests/integration/test_abac_query_isolation.py` | Not isolated into a dedicated required test subset. |
| Cross-tenant resource matrix checks | integration suite | Yes (inside backend pytest run) | `tests/integration/test_cross_tenant_resource_matrix.py`, `tests/integration/test_tenant_isolation.py` | Matrix expansion process for new endpoints is manual. |

## Supporting security implementation evidence

- Authorization model code: `backend/app/modules/rbac_abac/permission_codes.py`, `backend/app/modules/rbac_abac/rules.py`, `backend/app/modules/rbac_abac/engine.py`.
- Tenant-sensitive file paths enforce row ownership in API and service layers: `backend/app/modules/files/api.py`, `backend/app/modules/files/service.py`, `backend/app/modules/files/storage.py`.

## Explicit current gaps

1. No single “security sign-off bundle” artifact is produced per CI run.
2. Browser e2e workflow (`.github/workflows/e2e-smoke.yml`) is not a strict security gate and can skip credentialed checks when secrets are unset.
3. Security gate ownership/escalation path is not encoded in repository docs.

## Acceptance criteria for this workstream

- Every required security gate is mapped to a blocking CI step or mandatory test subset.
- Security gate failures are traceable to a single evidence bundle per run.
- RBAC/ABAC and tenant-isolation verification remain mandatory for release candidate promotion.
