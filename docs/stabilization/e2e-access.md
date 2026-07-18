# E2E access mapping (matrix → tests)

This document fixes the CI policy for frontend Playwright smoke and backend access matrix checks.

## Frontend smoke policy (mandatory vs optional)

### Mandatory (always runs, no external creds)

These tests are **blocking** and run in the `playwright-smoke-minimal` job:

- `frontend/e2e/smoke.spec.ts` → `smoke > mandatory (no external creds) > login page renders`
- `frontend/e2e/smoke.spec.ts` → `smoke > mandatory (no external creds) > protected route redirects to login when logged out`
- `frontend/e2e/smoke.spec.ts` → `smoke > mandatory (no external creds) > unauthorized/denied route shows access denied page`

Execution contract:

- run with `E2E_START_SERVER=1`;
- never skipped by missing credentials;
- failure in this subset fails the workflow.

### Extended credential matrix (separate stage)

These tests run in `playwright-smoke-credential` after minimal smoke passes.

Credential sources (`matrix.credential_source`):

1. `bootstrap_local` (**required**) — local deterministic users are created in CI job.
2. `repo_secrets` (**optional**) — same credential tests, but emails/passwords come from repository secrets (runs only when secrets are present).

Extended subset (`--grep "credential-based flows"`):

- `R11 login happy path`
- `R11 documents list after login`
- `R11b documents loading screen settles`
- `navigation regression: command bar, top nav links and breadcrumb`
- `navigation regression: mobile menu opens and routes`
- `logout returns to login`
- `R12 limited user denied on documents route`
- `login wrong password shows inline error`

## Deterministic bootstrap users in CI

`playwright-smoke-credential` always starts local backend and provisions users inside the job:

- owner-like user (`E2E_USER_*`) for happy path;
- limited user (`E2E_LIMITED_USER_*`) with `student` role for deny path (`/documents` -> `Доступ ограничен`).

Default deterministic credentials for `bootstrap_local`:

- `E2E_USER_EMAIL=e2e.owner.demo@example.com`
- `E2E_USER_PASSWORD=OwnerDemo123!`
- `E2E_LIMITED_USER_EMAIL=e2e.student.demo@example.com`
- `E2E_LIMITED_USER_PASSWORD=StudentDemo123!`
- `E2E_TENANT=demo`

When `repo_secrets` is selected, the same env keys are populated from repository secrets.

## Fallback policy

- **Always required:** minimal no-cred smoke (`mandatory (no external creds)`).
- **Required extension:** `bootstrap_local` credential matrix row (deterministic users, no external secret dependency).
- **Optional extension:** `repo_secrets` matrix row (runs only if all E2E secrets are configured).

If secrets are absent, credential coverage is still preserved by `bootstrap_local`; only the `repo_secrets` row is skipped.

---

## Backend access mapping

This section maps `docs/stabilization/rbac-matrix.md` rows to backend tests. Each row should have both a positive and a negative assertion path where practical.

| matrix row | positive case(s) | negative case(s) |
|---|---|---|
| owner/admin broad access in-tenant | `tests/test_next12_rbac_abac.py::test_owner_can_do_everything_in_tenant`; `tests/test_next9_authz.py::test_owner_can_list_documents_across_scope` | cross-tenant rejection: `tests/test_rbac_abac.py::test_cross_tenant_write_is_rejected` |
| auditor_ro read-only behavior | read/list allowed implicitly by role map checks in `tests/test_next12_rbac_abac.py` | `tests/test_next12_rbac_abac.py::test_auditor_ro_cannot_create_or_update`; `tests/test_next9_authz.py::test_auditor_cannot_update_incident` |
| student/instructor training permissions | (instructor positive covered by role permission map in `app.core.rbac_abac.ROLE_PERMISSIONS`) | `tests/e2e/access/test_access_enforcement_matrix.py::test_direct_api_create_is_denied_for_low_privilege_user` |
| scope-based ABAC company/contractor controls | `tests/test_next9_authz.py::test_inspector_contractor_reads_within_contractor` | `tests/test_next9_authz.py::test_hse_specialist_denied_on_foreign_company`; `tests/test_next12_rbac_abac.py::test_executor_cannot_access_other_project` |
| cross-tenant deny independent of UI | in-tenant business call success paths across API tests | `tests/e2e/access/test_access_enforcement_matrix.py::test_cross_tenant_header_is_denied_even_for_privileged_user`; `tests/test_jwt_xtenant_uuid_scope_mismatch.py::test_jwt_for_test_tenant_with_x_tenant_uuid_of_beta_returns_403` |
| unauthorized file access deny | same-company download/detail success already covered in `tests/test_files_upload.py` happy paths | `tests/e2e/access/test_access_enforcement_matrix.py::test_file_detail_denies_client_from_other_company`; `tests/test_files_upload.py::test_download_denies_company_mismatch`; `tests/test_files_upload.py::test_download_denies_cross_tenant` |
| stale/low-privilege session reuse hardening | fresh privileged token can perform admin actions in existing CRUD tests | `tests/e2e/access/test_access_enforcement_matrix.py::test_stale_admin_token_is_denied_after_role_downgrade` |

## Stabilization intent

- Assert deny decisions at direct API layer (not only via hidden UI controls).
- Keep tenant and ABAC checks active even when route/UI behavior changes.
- Lock regression for stale privilege reuse by requiring server-side role reconciliation against persisted user role state.
