# CHANGELOG

## 2026-03-21
- Added canonical docs: `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`, `docs/DEMO_ACCESS.md`, `docs/OWNER_ADMIN_ACCESS.md`, `docs/USER_ACCESS_AND_ROLES.md`.
- Hardened template catalog contract with category/status/scope fields.
- Fixed template version upload so the uploaded version becomes `current_version_id` consistently.
- Normalized generation-time template resolution to support both `code` and legacy `name` lookups.
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
