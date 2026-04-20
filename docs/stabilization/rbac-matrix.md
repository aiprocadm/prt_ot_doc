# RBAC/ABAC stabilization matrix (implemented behavior)

This matrix is derived from the current backend authorization code paths and the existing access docs:

- Core role/permission engine: `backend/app/core/rbac_abac.py`.
- Request-time permission dependency guards: `backend/app/modules/rbac_abac/deps.py` + `backend/app/modules/rbac_abac/engine.py`.
- Authentication context and tenant/company hard checks: `backend/app/core/security.py`.
- Representative guarded routes: `backend/app/api/routes/training_next.py`, `backend/app/api/routes/risk_enterprise.py`, `backend/app/api/routes/jobs.py`, `backend/app/api/routes/files.py`.
- Existing documentation context: `docs/security/rbac_abac.md`, `docs/USER_ACCESS_AND_ROLES.md`, `docs/FRONTEND_ROUTES_AND_PERMISSIONS.md`.

## Matrix

| role | tenant scope | action | UI expectation | API expectation | allow/deny | audit expectation |
|---|---|---|---|---|---|---|
| owner/admin | same tenant | `*` on mapped resources | Full UI, including create/update/delete/operational actions | `PolicyEngine` grants broad permissions (`owner`/`admin` full map) | Allow | Authz decisions should be auditable when explicit logging hook is used (`audit_authz_decision`); deny events should not occur in normal flow. |
| auditor_ro | same tenant | write-like actions (`create/update/delete/approve/sign/export`) | UI should be read-only; action controls hidden/disabled | Engine explicitly blocks non-read/list for `auditor_ro` | Deny | `require_action` emits `access_deny` audit event when dependency is used and DB session is present. |
| student | same tenant | `trainings.create` (or `trainings.update`) | No create/edit actions in Training UI | `/api/v1/training/*` write endpoints guarded by `require_permission` | Deny (403 `AUTHZ_DENIED`) | Denied dependency checks should write `access_deny` with reason `missing_permission`. |
| instructor | same tenant | `trainings.create`/`trainings.update` | Training authoring actions visible | `trainings:create/update` is in role permission map | Allow | Successful writes should still produce domain audit events where route decorators/services log them. |
| hse_specialist with scoped `company_ids` | same tenant, foreign company resource | read document/incident/risk object from foreign company | UI may show list widgets, but foreign entities should be absent/blocked | ABAC scope check (`company_id`) rejects mismatched scope | Deny | Denied decision reason should be `scope_mismatch` when policy engine path is used. |
| inspector_contractor with scoped `contractor_ids` | same tenant, own contractor resource | inspections/incidents read | UI limited to assigned contractor context | Scope match in `_scope_check` permits read/list | Allow | Access decisions can be traced via `authz_decision` events when hook is called. |
| any authenticated role | cross-tenant request (JWT tenant ≠ `X-Tenant`) | any business action | UI tenant switch should not allow stale cross-tenant execution | tenant middleware/dependency must reject before business handler | Deny (403 `TENANT_SCOPE_MISMATCH`) | Tenancy mismatch is logged by tenant guard paths; no business mutation should occur. |
| client/client_user | same tenant, file owned by another company | file details/download | File row may be discoverable only by id, but action buttons should not imply access | files API enforces tenant row + company ABAC (`ensure_company_access`) | Deny (403) | Deny should be reflected in authz/file-deny telemetry and no file payload leak. |
| token with stale high privilege, DB role downgraded | same tenant | privileged write API reuse | UI should require re-login/reduced privileges after downgrade | server must derive effective roles from persisted user role assignment (not stale token claims alone) | Deny | Denial should be explicit (`AUTHZ_DENIED`/insufficient role) and auditable. |

## Notes for stabilization

- There are two permission vocabularies in code (`app.core.rbac_abac.ROLE_PERMISSIONS` and `app.modules.rbac_abac.rules.ROLE_PERMISSIONS`). Stabilization tests intentionally target real route guards to lock expected runtime behavior.
- UI visibility is non-authoritative. Server-side `rbac()/abac()` + `require_permission()` checks are the enforcement boundary.
