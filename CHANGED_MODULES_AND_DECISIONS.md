# CHANGED_MODULES_AND_DECISIONS

## 2026-03-21 wave

### Template contract normalization
**Changed modules/files**
- `backend/app/modules/templates/schemas.py`
- `backend/app/api/v1/router.py`
- `backend/app/schemas/common.py`
- `frontend/src/types/dto/templates.ts`
- `frontend/src/types/forms/templates.ts`
- `frontend/src/features/templates/TemplateFormDialog.tsx`
- `frontend/src/features/templates/TemplateDetails.tsx`
- `backend/app/api/routes/notifications.py`
- `backend/app/modules/notifications/__init__.py`
- `backend/app/modules/notifications/schemas.py`
- `backend/app/modules/notifications/service.py`
- `tests/api/test_notifications_calendar_api.py`

**Decision**
- Keep storage backward-compatible by persisting scope/category in `metadata_json`, while exposing a normalized API/UI contract now.

**Why**
- Repo already had template entities and working flows; big-bang schema rewrite would be risky.
- The next wave needs a clear canonical contract in code and docs.

### Generation lookup hardening
**Changed files**
- `backend/app/api/routes/documents.py`
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
- Resolve templates by `code` or legacy `name`.

**Why**
- Existing code used both conventions in different places, creating fragile production behavior.

### Access/bootstrap documentation
**Changed docs**
- `README.md`
- `docs/DOCUMENT_CORE.md`
- `docs/TEMPLATE_UPLOAD_AND_RENDERING.md`
- `docs/DEMO_ACCESS.md`
- `docs/OWNER_ADMIN_ACCESS.md`
- `docs/USER_ACCESS_AND_ROLES.md`
- root release/gap/acceptance docs.
## 2026-03-21
- Normalized template API DTOs so frontend can work with backend-native scope/type/current-version/version-history fields.
- Added explicit template scope documentation and surfaced scope metadata in the templates UI.
- Documented canonical demo access, owner bootstrap and user access issuance flows from repo code instead of relying on branch memory.
- Removed duplicate template router/schema/frontend form fragments so the repository has one coherent custom-template contract again.
