# CHANGELOG

## 2026-03-26
- Stabilized tenancy session propagation for FK-backed tenant models by separating `tenant_id`, `tenant_slug`, and `tenant_schema` in session context and preventing slug autofill into UUID-backed `tenant_id` fields.
- Fixed demo bootstrap so FK-backed entities use the real tenant UUID instead of tenant slug values.
- Formalized stateless logout with `POST /auth/logout -> 204 No Content` and documented that clients must clear local tokens because backend-side refresh-token revocation is not yet implemented.
- Removed unreachable quota code from `backend/app/api/v1/router.py` and kept `assert_quota(...)` as the single active generation quota path.
- Hardened CORS configuration so credentialed requests cannot start with wildcard origins; added settings and app-factory regression coverage for this.
- Realigned `docs/openapi.yaml` with the runtime auth contract and added contract tests for `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/logout`, `/api/v1/auth/me`, and `/api/v1/auth/me/permissions`.
- Removed critical runtime route collisions on canonical URLs for prescriptions, files, training certificates, approvals, and EDO list endpoints by moving overlapping legacy aliases to explicit namespaced/versioned paths; added a regression test for duplicate path+method registration on these critical routes.
- Fixed runtime schema bootstrap for tenants with explicit `schema_name`: session bootstrap, dependency resolution, dev bootstrap, demo bootstrap, and tenant bootstrap service now create/use the recorded schema instead of recomputing `tenant_<slug>`.
- Disabled implicit schema auto-create in ordinary runtime session paths by default behind `RUNTIME_SCHEMA_BOOTSTRAP`; explicit bootstrap routines remain responsible for intentional schema creation in dev/test setup flows.

## 2026-03-21
- Added canonical docs: `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`, `docs/DEMO_ACCESS.md`, `docs/OWNER_ADMIN_ACCESS.md`, `docs/USER_ACCESS_AND_ROLES.md`.
- Hardened template catalog contract with category/status/scope fields.
- Fixed template version upload so the uploaded version becomes `current_version_id` consistently.
- Normalized generation-time template resolution to support both `code` and legacy `name` lookups.
- Removed duplicate/broken template schema and router fragments that were causing invalid backend/frontend template contracts.
- Restored a coherent templates UI contract by fixing DTOs, form schema and the template form dialog around `scope.type`.
- Added regression tests for template scope metadata and current-version linking.

### Added
- Introduced a dedicated notifications application module at `backend/app/modules/notifications/` with explicit schemas and service boundaries.
- Added canonical docs: `docs/TRAINING_AND_LMS.md`, `docs/RISK_ENGINE.md`, `docs/ACCEPTANCE_SCENARIOS.md`, and this changelog.
- Added `CHANGED_MODULES_AND_DECISIONS.md` to document the wave-level architectural decisions.

### Changed
- Slimmed `backend/app/api/routes/notifications.py` so the router now delegates business logic to the notification application service instead of querying models directly.
- Normalized notification enum validation so invalid `status`/`priority`/`channel`/`type` values fail with structured 422 responses instead of leaking `ValueError` behavior.
- Hardened notification query validation so malformed `cursor` values and unsupported calendar `source` values now return the canonical structured 422 contract instead of generic failures or silent empty responses.
- Expanded notification API acceptance coverage in `tests/api/test_notifications_calendar_api.py`.
- Reworked unread counting to use aggregate SQL count semantics instead of materializing all unread notifications in memory.
- Updated acceptance, gap, release-readiness, and architecture docs to reflect the real state of notifications/training/risk hardening.
- enhanced template DTOs with scope/type/current-version/version-history;
- added template version patch endpoint for lifecycle updates;
- updated templates UI to show scope/type and use backend-aligned DTOs;
- added canonical docs for template upload/rendering, demo access, owner/admin access and user access issuance.
