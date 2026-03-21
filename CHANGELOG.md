# CHANGELOG

## 2026-03-21
- Added canonical docs: `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`, `docs/DEMO_ACCESS.md`, `docs/OWNER_ADMIN_ACCESS.md`, `docs/USER_ACCESS_AND_ROLES.md`.
- Hardened template catalog contract with category/status/scope fields.
- Fixed template version upload so the uploaded version becomes `current_version_id` consistently.
- Normalized generation-time template resolution to support both `code` and legacy `name` lookups.
- Added regression tests for template scope metadata and current-version linking.
