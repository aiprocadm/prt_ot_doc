# File perimeter hardening plan

## Primary perimeter decision

- **Primary perimeter under `/api/v1/files`:** `backend/app/modules/files/api.py`.
- **Legacy compatibility perimeter:** `backend/app/api/routes/files.py` is exposed only via `/api/v1/files-legacy` and controlled by `ENABLE_FILES_LEGACY_ROUTES`.
- In **production**, legacy compatibility is disabled by default (`ENABLE_FILES_LEGACY_ROUTES=false`).

## Endpoint → control → regression-test map

| Endpoint (canonical) | Control(s) | Regression test(s) |
|---|---|---|
| `GET/POST /api/v1/files/{file_id}/download-url` | ABAC read roles (`admin`,`employee`,`client_admin`,`client_user`), tenant ownership check, company-level ABAC for client roles, clean-only download, deny audit (`file.download_url.denied`) for company/clean/tenant-key denials | `backend/tests/test_files_access_parity.py::test_canonical_files_roles_match_legacy_contract`, `backend/tests/test_files_security_negative_cases.py::test_get_signed_download_url_rejects_cross_tenant_access`, `...::test_get_signed_download_url_rejects_cross_company_client_access`, `...::test_get_signed_download_url_rejects_non_clean_file`, `...::test_company_scope_denials_are_audited_for_protected_file_actions` |
| `POST /api/v1/files/{file_id}:signed-url` | Same controls as canonical download URL issue path above | Same signed-url service deny tests as above |
| `GET /api/v1/files-legacy/{file_id}` | Legacy read compatibility only; tenant-row check + company ABAC for client roles + presign only when AV status is `CLEAN` | `backend/tests/test_files_access_parity.py::test_legacy_upload_and_download_dependencies_match_canonical_tenant_and_abac_contract` + legacy upload/download regression set in `tests/test_files_upload.py` |
| `DELETE /api/v1/files/{file_id}` | ABAC write roles (`admin`,`employee`), tenant ownership check, company-level ABAC for client roles (deny on mismatch), deny audit (`file.delete.denied`) | `backend/tests/test_files_security_negative_cases.py::test_delete_file_rejects_cross_tenant_access`, `...::test_delete_file_rejects_cross_company_client_access`, `...::test_company_scope_denials_are_audited_for_protected_file_actions` |
| `POST /api/v1/files/upload-multipart`, `POST /api/v1/files/presign-upload`, `POST /api/v1/files/init-upload`, `POST /api/v1/files/{file_id}/new-version` | ABAC write roles, upload size/mime/extension policy, dangerous double-extension deny | `backend/tests/test_files_access_parity.py::test_canonical_files_roles_match_legacy_contract`, `backend/tests/test_files_security_negative_cases.py::test_create_upload_session_rejects_dangerous_double_extension` |
| `POST /api/v1/files/{file_id}:link` | ABAC write roles, tenant ownership check, company-level ABAC for client roles, clean-only guard for privileged link roles (`output`,`signature`,`receipt`), deny audit (`file.link.denied`) | `backend/tests/test_files_security_negative_cases.py::test_company_scope_denials_are_audited_for_protected_file_actions`, `...::test_link_file_rejects_non_clean_guarded_role_and_emits_audit` |

## Legacy routing policy

- Keep legacy endpoints out of canonical `/files` include tree.
- If compatibility is required during transition, legacy stays under explicit prefix `/files-legacy` only.
- Legacy router is enabled only via `ENABLE_FILES_LEGACY_ROUTES=true`; with flag off, `/files-legacy/*` must not be registered.
- No new feature work is allowed in the legacy router.
- Legacy compatibility may receive bugfixes only when they preserve canonical security semantics (tenant/company/role guards and deny observability).

### Compatibility boundary regression checks

- `backend/tests/test_route_group_registry.py::test_files_router_registration_switches_with_legacy_flag`
- `backend/tests/test_files_access_parity.py::test_legacy_upload_and_download_dependencies_match_canonical_tenant_and_abac_contract`

## Rollback note (critical incident)

If a critical incident requires immediate temporary rollback to old behavior:

1. Set `ENABLE_FILES_LEGACY_ROUTES=true` in the deployment environment.
2. Redeploy API pods/processes so settings are reloaded.
3. Legacy endpoints become available under `/api/v1/files-legacy/*`.
4. Open a follow-up task to disable legacy routing again and return to canonical-only perimeter (`ENABLE_FILES_LEGACY_ROUTES=false`).
