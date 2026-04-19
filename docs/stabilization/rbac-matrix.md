# RBAC/ABAC Matrix (Stabilization)

_Last updated: 2026-04-19._

This matrix is evidence-based and reflects code/tests currently present in the repository.

## Permission source evidence

- Permission catalog: `backend/app/modules/rbac_abac/permission_codes.py`.
- Role permission mapping: `backend/app/modules/rbac_abac/rules.py`.
- Runtime enforcement plumbing: `backend/app/modules/rbac_abac/engine.py`, `backend/app/modules/rbac_abac/deps.py`.

## Endpoint behavior evidence matrix

| Scenario | Expected result | Evidence test(s) | Current state |
|---|---|---|---|
| Client user accessing managed resources (e.g., companies) | 403 FORBIDDEN | `tests/test_rbac_abac.py::test_client_user_cannot_access_managed_resources` | Covered |
| Cross-tenant write with mismatched tenant header/token scope | 403 TENANT_SCOPE_MISMATCH | `tests/test_rbac_abac.py::test_cross_tenant_write_is_rejected` | Covered |
| Cross-tenant read with mismatched tenant scope | 403 TENANT_SCOPE_MISMATCH | `tests/test_rbac_abac.py::test_cross_tenant_read_is_forbidden` | Covered |
| Non-admin trying to assign roles via admin endpoint | 403 | `tests/integration/test_admin_user_roles.py::test_non_admin_cannot_assign_roles` | Covered |
| Admin assigns user roles | 200 with assigned roles | `tests/integration/test_admin_user_roles.py::test_admin_can_assign_roles` | Covered |
| Assigned role affects downstream access | No 403 at protected endpoint (business validation may still fail) | `tests/integration/test_admin_user_roles.py::test_assigned_roles_grant_access` | Covered |

## Role-map implementation notes (current)

- `backend/app/modules/rbac_abac/rules.py` defines a compact role map for policy evaluation (`owner`, `admin`, `auditor_ro`, `manager`).
- `backend/app/modules/rbac_abac/permission_codes.py` contains a broader MVP permission list used by higher-level permission modeling.

## Explicit current gaps

1. No generated artifact that verifies every endpoint is mapped to a tested permission code.
2. Potential mismatch risk between concise `rules.py` role-permission map and larger `permission_codes.py` catalog is not automatically audited.
3. No CI check currently fails if a new protected endpoint is added without updating this matrix.

## Acceptance criteria for this workstream

- Matrix stays synchronized with code and tests whenever RBAC-protected endpoints change.
- New protected endpoints include at least one allow and one deny test referencing tenant scope.
- Drift between permission catalog and enforced role map is checked by automated test or script.
