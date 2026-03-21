# CHANGELOG

## 2026-03-21

### Added
- Introduced a dedicated notifications application module at `backend/app/modules/notifications/` with explicit schemas and service boundaries.
- Added regression tests in `backend/tests/test_notifications_service.py` for unread counts, mark-read behavior, and enum validation.
- Added canonical docs: `docs/TRAINING_AND_LMS.md`, `docs/RISK_ENGINE.md`, `docs/ACCEPTANCE_SCENARIOS.md`, and this changelog.
- Added `CHANGED_MODULES_AND_DECISIONS.md` to document the wave-level architectural decisions.

### Changed
- Slimmed `backend/app/api/routes/notifications.py` so the router now delegates business logic to the notification application service instead of querying models directly.
- Normalized notification enum validation so invalid `status`/`priority`/`channel`/`type` values fail with structured 422 responses instead of leaking `ValueError` behavior.
- Reworked unread counting to use aggregate SQL count semantics instead of materializing all unread notifications in memory.
- Updated acceptance, gap, release-readiness, and architecture docs to reflect the real state of notifications/training/risk hardening.
