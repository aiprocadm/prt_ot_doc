# FRONTEND_TEST_PLAN

## Objectives

- Keep routing, RBAC, tenant safety, and API-driven page behavior stable.
- Prevent regressions in newly implemented v1 sections.
- Define a practical progression from current unit/component tests to broader end-to-end confidence.

## Current quality gate commands

Run from frontend directory:

1. npm run lint
2. npm run typecheck
3. npm run test

Current status after this cycle:

- lint: pass
- typecheck: pass
- test: pass

## Newly added tests in this cycle (Cycle 1)

1. src/__tests__/PpePage.test.tsx
- Verifies data load and rendering for PPE summary/table states.
- Verifies retry/error paths with mocked API behavior.

2. src/__tests__/CrmFinancePage.test.tsx
- Verifies orders/invoices/billing summary rendering with mocked API responses.
- Verifies empty-state behavior where appropriate.

3. src/__tests__/IntegrationsPage.test.tsx
- Verifies integrations dashboard rendering for endpoints, deliveries, and outbox events.
- Verifies webhook endpoint creation action triggers API call.

## Newly added tests in this cycle (Cycle 2 — MVP+/v1 hardening)

4. src/__tests__/IncidentsPage.test.tsx
- Verifies incidents list renders after API load.
- Verifies empty state when API returns no data.
- Verifies "Зарегистрировать инцидент" button opens create dialog and dialog contains title field.

5. src/__tests__/InspectionsPage.test.tsx
- Verifies inspections list renders with expected row data (authority field).
- Verifies empty state when API returns no data.
- Verifies "Создать проверку" button opens create dialog and dialog contains authority field.

6. src/__tests__/ApprovalsInboxPage.test.tsx
- Verifies tasks tab renders task cards when `listMyTasks("open")` returns data.
- Verifies empty state message "Открытых задач нет" shown when all lists are empty.

All Cycle 2 tests use `vi.hoisted()` for correct mock hoisting in Vitest.

## Test suite total

| Cycle | Tests added | Total |
|-------|-------------|-------|
| Before Cycle 1 | — | ~40 |
| Cycle 1 | ~9 | 49 |
| Cycle 2 | 8 | 57 |

## Regression areas covered by existing tests

1. Route shell and protected behavior
- Existing tests around router/protected paths and layout behavior.

2. Ability/permission logic
- Existing tests around permission resolution and route access decisions.

3. Core document/domain modules
- Existing tests for key legacy pages/components remain in suite.

## Gaps in automated testing

1. End-to-end role + tenant matrix
- Missing full browser-level checks for tenant isolation and no-access redirects across all major route groups.

2. Mutation-heavy workflows
- Limited test depth for create/edit/approve/sign flows in some sections.

3. Deep edge-case contract handling
- Additional coverage needed for malformed payloads, partial backend responses, and pagination/filter combinations.

4. Feature flag route/nav visibility
- Need dedicated tests for feature toggles (example: EDO visibility behavior).

## Planned test expansion (priority order)

1. Critical RBAC E2E suite
- Scenarios:
  - user without permission is redirected to no-access
  - route visible/invisible in side nav based on permission
  - tenant switch does not leak data across tenants

2. Operational page behavior suite
- PPE/warehouse/training/incidents/inspections:
  - load success/error/empty
  - filter changes trigger re-fetch
  - refresh action re-requests server data

3. Integrations workflow suite
- endpoint create/test actions
- delivery and outbox list refreshes
- error rendering on failed integration actions

4. CRM/finance workflow suite
- status categorization for invoices
- billing summary rendering on different subscription states

## Test data and mocking rules

1. Prefer deterministic fixtures for all list endpoints.
2. Keep one fixture per domain scenario (happy path, empty, API error).
3. Use hoisted-safe mock initialization in Vitest files to avoid module-evaluation race issues.
4. Avoid brittle selectors when duplicate visible labels are valid in UI.

## Definition of done for frontend changes

Any frontend feature change is complete when:

1. Route and permission guard are defined and validated.
2. Loading/error/empty and success states are implemented.
3. At least one component/page test exists for primary behavior.
4. lint, typecheck, and test pass in CI/local.
5. Route/permission documentation is updated if access model changes.
