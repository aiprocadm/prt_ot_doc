# E2E access mapping (matrix → tests)

This document maps `docs/stabilization/rbac-matrix.md` rows to concrete tests. Each row should have both a positive and a negative assertion path where practical.

## Mapping

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
