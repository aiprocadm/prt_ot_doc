# UX Sprint Execution Checklist

Практический чеклист для следующих двух спринтов по фронтенду.

## Sprint 1 (P1)

### 1) Key E2E scenarios without skip

- [ ] Stabilize env bootstrap for key scenarios.
  - Files:
    - `frontend/e2e/key-scenarios.spec.ts`
    - `frontend/playwright.config.ts`
    - `frontend/e2e.env.example`
    - `frontend/scripts/run-e2e-key-scenarios.ps1`
- [ ] Ensure scenarios execute (not skipped) in local and CI with test credentials.
  - Files:
    - `frontend/package.json`
    - CI workflow files (if present)
- [ ] Add a short "how to run" section for QA handoff.
  - Files:
    - `frontend/README.e2e.md`
    - `docs/stabilization/TEST_COVERAGE_GAPS.md`

Definition of done:
- `npm run e2e:key-scenarios` runs 4 tests (no skip in configured env).

---

### 2) Unified post-create UX pattern

- [ ] Companies: keep created entity in focus and show clear next action.
  - File: `frontend/src/pages/companies/CompaniesPage.tsx`
- [ ] Documents: explicit create CTA in header + predictable next step.
  - File: `frontend/src/pages/documents/DocumentsPage.tsx`
- [ ] Tasks: after create, set focus via query (`task_id`) and keep context.
  - File: `frontend/src/pages/tasks/TasksPage.tsx`
- [ ] Inspections: after create, set focus (`entity_type/entity_id/view`) and keep context.
  - File: `frontend/src/pages/inspections/InspectionsPage.tsx`

Definition of done:
- User always sees "what happened" and "what to do next" after create.

---

### 3) URL-state consistency for filters

- [ ] Tasks: query sync for `type/overdue/priority` (already started, finalize edge-cases).
  - File: `frontend/src/pages/tasks/TasksPage.tsx`
- [ ] Inspections: query sync for `status` (already started, finalize edge-cases).
  - File: `frontend/src/pages/inspections/InspectionsPage.tsx`
- [ ] Extend same behavior to priority pages:
  - [ ] Notifications (`status/channel/priority/type`)
    - File: `frontend/src/pages/notifications/NotificationsPage.tsx`
  - [ ] Reports (date range)
    - File: `frontend/src/pages/reports/ReportsPage.tsx`
  - [ ] Calendar (`mode/source`)
    - File: `frontend/src/pages/calendar/CalendarPage.tsx`

Definition of done:
- Refresh/share/back preserves user-selected filters on listed pages.

---

### 4) Human-readable labels (status/type codes)

- [ ] Inspections: labels for type/status in table/focus/filter.
  - File: `frontend/src/pages/inspections/InspectionsPage.tsx`
- [ ] Training: labels for completion statuses and material types.
  - File: `frontend/src/pages/training/TrainingPage.tsx`
- [ ] Risk: labels for assessment statuses and risk levels.
  - Files:
    - `frontend/src/features/risk/RiskAssessmentsTable.tsx`
    - `frontend/src/features/risk/RiskAssessmentForm.tsx`

Definition of done:
- No raw backend-like enum codes visible on key user screens.

## Sprint 2 (P2)

### 5) Unified page-state behavior

- [ ] Standardize loading/empty/error/retry/help blocks on major pages.
  - Files (target set):
    - `frontend/src/pages/*/*.tsx`
    - `frontend/src/components/common/EmptyState.tsx`
    - `frontend/src/components/common/ErrorState.tsx`
    - `frontend/src/components/common/LoadingScreen.tsx`

Definition of done:
- All major pages follow one recognizable page-state pattern.

---

### 6) Navigation accelerators

- [ ] Quick actions from top-level screens.
- [ ] Recently viewed / pinned sections coherence.
- [ ] Global search behavior consistency.
  - Likely files:
    - `frontend/src/components/layout/TopNav.tsx`
    - `frontend/src/components/layout/SideNav.tsx`
    - `frontend/src/components/GlobalSearch.tsx`
    - `frontend/src/pages/dashboard/DashboardPage.tsx`

Definition of done:
- Frequent actions reachable with fewer clicks and no context breaks.

---

### 7) UX behavior tests (RTL + E2E)

- [ ] Add/extend RTL tests for:
  - query sync behavior
  - post-create focus behavior
  - CTA visibility/disabled state by permission
  - Files:
    - `frontend/src/__tests__/TasksPage.test.tsx`
    - `frontend/src/__tests__/InspectionsPage.test.tsx`
    - `frontend/src/__tests__/TrainingPage.test.tsx`
    - `frontend/src/__tests__/RiskPage.test.tsx`
- [ ] Add compact e2e assertions for key IA behavior.
  - Files:
    - `frontend/e2e/key-scenarios.spec.ts`
    - `frontend/e2e/smoke.spec.ts`

Definition of done:
- UX regressions are caught by automated tests, not manually.

---

### 8) Performance pass on heavy screens

- [ ] Identify heavy tables and add virtualization where needed.
- [ ] Add memoization for expensive lists/cards.
- [ ] Review lazy-loading/code splitting for non-critical routes.
  - Likely files:
    - `frontend/src/components/common/DataTable.tsx`
    - heavy `frontend/src/pages/*/*.tsx`
    - router/page registry files

Definition of done:
- No notable UX lag on production-like datasets for key registries.

## Validation Checklist (after each milestone)

- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run test -- TasksPage InspectionsPage TrainingPage RiskPage`
- [ ] `cd frontend && npm run e2e:key-scenarios` (in configured env)
- [ ] Update progress notes:
  - `docs/architecture/UX_ITERATION_PROGRESS.md`

