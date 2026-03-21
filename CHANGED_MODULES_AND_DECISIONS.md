# CHANGED_MODULES_AND_DECISIONS

## 2026-03-21 wave

### 1. Notifications API boundary hardening
**Changed modules/files**
- `backend/app/api/routes/notifications.py`
- `backend/app/modules/notifications/__init__.py`
- `backend/app/modules/notifications/schemas.py`
- `backend/app/modules/notifications/service.py`
- `tests/api/test_notifications_calendar_api.py`

**Decision**
- Move notification listing, mark-read mutation, settings CRUD, template CRUD, and calendar-event composition out of the FastAPI router into an application-service layer.

**Why**
- The previous router contained query construction, enum parsing, mutation logic, and calendar aggregation directly in the API layer.
- Invalid enum-like query parameters could raise inconsistent exceptions.
- Unread counts were computed by loading rows rather than via aggregate count.

**Result**
- Router is thinner and closer to transport-only responsibilities.
- Notification filters now fail predictably with structured validation payloads.
- Cross-entity notification/calendar behavior remains backward-compatible at the endpoint level.

### 1.1. Notification query-contract completion
**Changed modules/files**
- `backend/app/modules/notifications/service.py`
- `tests/api/test_notifications_calendar_api.py`
- `docs/API_OVERVIEW.md`
- `docs/ACCEPTANCE_SCENARIOS.md`
- `ACCEPTANCE_TEST_MATRIX.md`

**Decision**
- Finish the notification query normalization pass by validating cursor pagination input and calendar `source` filters in the same application service boundary as enum filters.

**Why**
- The router had already been thinned, but malformed `cursor` values could still bubble into `datetime.fromisoformat(...)` and become generic server errors.
- Calendar aggregation silently accepted arbitrary `source` strings and returned misleading empty results instead of an explicit contract failure.

**Result**
- Notifications endpoints now reject malformed cursor and source values with the canonical structured 422 payload.
- Acceptance evidence and docs now describe the full query-validation surface instead of only enum filters.

### 2. Documentation normalization for next-wave self-sufficiency
**Changed docs**
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULES.md`
- `docs/API_OVERVIEW.md`
- `docs/WORKFLOWS_AND_EVENTS.md`
- `docs/TESTING.md`
- `docs/TRAINING_AND_LMS.md`
- `docs/RISK_ENGINE.md`
- `docs/ACCEPTANCE_SCENARIOS.md`
- `docs/audit/TZ_COVERAGE_MATRIX.md`
- `ACCEPTANCE_TEST_MATRIX.md`
- `GAP_REPORT.md`
- `RELEASE_READINESS.md`
- `KNOWN_LIMITATIONS.md`
- `CHANGELOG.md`

**Decision**
- Prefer explicit “full / partial / foundation” wording over optimistic descriptions where modules are real but not yet fully acceptance-closed.

**Why**
- The next task must be able to infer true repo status from docs alone.
- Training, risk, and notifications needed clearer canonical-path references and implementation posture.

**Result**
- The repository now documents the hardened notifications boundary and more accurately describes partial domains without deleting working functionality.
