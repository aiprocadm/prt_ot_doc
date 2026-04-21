# File perimeter hardening plan

## Primary perimeter decision

- **Primary perimeter under `/api/v1/files`:** `backend/app/modules/files/api.py`.
- **Legacy compatibility perimeter:** `backend/app/api/routes/files.py` is exposed only via `/api/v1/files-legacy` and controlled by `ENABLE_FILES_LEGACY_ROUTES`.
- In **production**, legacy compatibility is disabled by default (`ENABLE_FILES_LEGACY_ROUTES=false`).

## Endpoint → control → regression-test map

| Endpoint (canonical) | Control(s) | Regression test(s) |
|---|---|---|
| `GET/POST /api/v1/files/{file_id}/download-url` | ABAC read roles (`admin`,`employee`,`client_admin`,`client_user`), tenant ownership check, company-level ABAC for client roles, clean-only download | `backend/tests/test_files_access_parity.py::test_canonical_files_roles_match_legacy_contract`, `backend/tests/test_files_security_negative_cases.py::test_get_signed_download_url_rejects_cross_tenant_access`, `...::test_get_signed_download_url_rejects_cross_company_client_access`, `...::test_get_signed_download_url_rejects_non_clean_file` |
| `POST /api/v1/files/{file_id}:signed-url` | Same controls as canonical download URL issue path above | Same signed-url service deny tests as above |
| `DELETE /api/v1/files/{file_id}` | ABAC write roles (`admin`,`employee`), tenant ownership check, company-level ABAC for client roles (deny on mismatch) | `backend/tests/test_files_security_negative_cases.py::test_delete_file_rejects_cross_tenant_access`, `...::test_delete_file_rejects_cross_company_client_access` |
| `POST /api/v1/files/upload-multipart`, `POST /api/v1/files/presign-upload`, `POST /api/v1/files/init-upload`, `POST /api/v1/files/{file_id}/new-version` | ABAC write roles, upload size/mime/extension policy, dangerous double-extension deny | `backend/tests/test_files_access_parity.py::test_canonical_files_roles_match_legacy_contract`, `backend/tests/test_files_security_negative_cases.py::test_create_upload_session_rejects_dangerous_double_extension` |

## Legacy routing policy

- Keep legacy endpoints out of canonical `/files` include tree.
- If compatibility is required during transition, legacy stays under explicit prefix `/files-legacy` only.
- No new feature work is allowed in the legacy router.

## Rollback note (critical incident)

If a critical incident requires immediate temporary rollback to old behavior:

1. Set `ENABLE_FILES_LEGACY_ROUTES=true` in the deployment environment.
2. Redeploy API pods/processes so settings are reloaded.
3. Legacy endpoints become available under `/api/v1/files-legacy/*`.
4. If you must mirror pre-hardening `/api/v1/files/*` compatibility in an emergency, temporarily change `backend/app/api/v1/route_groups.py` to mount `app.api.routes.files` under `/files` again and redeploy (time-boxed hotfix only).
5. Open a follow-up task to remove rollback routing and restore single-perimeter policy.
