# FRONTEND_GAP_ANALYSIS

## Scope and baseline

This document captures the frontend completion status for the OT/PB/PromBez/Ecology + EDO platform after the recent implementation cycle.

Baseline before this cycle:

- Several operational pages were static/demo-style and not backed by API calls.
- Mandatory sections (warehouse, crm-finance, integrations) were missing from route/navigation IA.
- RBAC matrix did not include enough role aliases and business permissions for v1 scenarios.
- Tests for the newly required operational pages were absent.

Current status after implementation:

- Core sections are now routed, guarded, and visible via permission-driven navigation.
- PPE, Training, Incidents, Inspections moved to API-backed data loading with loading/error/empty states.
- New v1 sections added: Warehouse, CRM/Finance, Integrations.
- Role and permission model expanded and normalized (permission aliases + role aliases).
- New frontend tests added for critical newly introduced pages.

## Completed items (implemented)

1. API-backed domain pages
- PPE page now loads catalog/issues/expiring data from backend API.
- Training page now loads courses and expiring certificates from backend API.
- Incidents page now loads incidents from backend API with status filtering.
- Inspections page now loads inspections from backend API with status filtering.

2. New mandatory sections and pages
- Warehouse page added for PPE inventory/active issues/expiring visibility.
- CRM/Finance page added for orders/invoices/billing summary.
- Integrations page added for webhook endpoints, deliveries, and outbox events.

3. RBAC and route coverage
- Permissions extended for warehouse, crm_finance, integrations, client_portal, generation, jobs.
- Role map expanded with operational/business roles.
- Alias normalization added for role and permission name compatibility.

4. Navigation and IA
- Side navigation reorganized into business sections:
  - Document flow
  - EDO and approvals
  - OT and PromBez
  - Fire safety
  - Business and analytics
  - Integrations and references
  - Administration

5. UX hardening
- Standardized usage of loading/error/empty states for new/rewritten pages.
- Removed explicit stub language in document wizard/preview completion points.

6. Quality gates
- ESLint config hardened to ignore generated artifacts (dist/coverage/node_modules).
- Frontend test suite passes after adding and stabilizing new tests.

## Completed items (Cycle 2 — MVP+/v1 hardening)

1. Create/edit flows for operational pages
- IncidentsPage: full create dialog with form (title, type, severity, datetime, company_id, site_id, description). `incidentsApi.create()` method added to API layer.
- InspectionsPage: full create dialog with form (company_id, inspection_type, authority, purpose, scheduled_at). `inspectionsApi.create()` method added to API layer.
- Both pages show toast on success/error and refresh list after creation.

2. ApprovalsInboxPage: phase-2 enhancement
- Added loading/error/empty states per tab.
- Added Breadcrumb, LoadingScreen, ErrorState components.
- Tables rendered for Processes, Signatures, and EDO envelopes tabs.
- Task count badge on "Мои задачи" tab trigger.

3. GeneratePackWizardPage: full 5-step wizard
- Step 1: select preset from API with loading/empty states.
- Step 2: JSON rows input with JSON validation.
- Step 3: idempotency key + dry-run toggle.
- Step 4: confirmation view with all parameters.
- Step 5: result display with generation ID, success/dry-run differentiation, and navigation.

4. SideNav completeness
- Added: Компании (`/companies`), Сотрудники (`/persons`), Пакеты (`/packs`), НПА (`/npa`) in business section.
- Added: Журнал аудита (`/audit`), Справочники (`/reference`), Настройки (`/settings`) in administration section.
- Icons added: BookOpen, Database, History, Settings from lucide-react.

5. AdminPage: proper navigation hub
- Replaced all placeholder stub cards with `Link`-based navigation cards.
- 10 subsystem cards: Биллинг, Outbox, Шаблоны, Макеты, Маршруты согласования, Интеграции, НПА, Журнал аудита, Настройки, Справочники.

6. ReportsPage: period filter and export
- Date range inputs (date_from / date_to) with default last-30-days preset.
- Apply filter button triggers list reload.
- XLSX and PDF export buttons call `/reports/export` with `responseType: blob` and automatic download.
- LoadingScreen added for loading state.

7. Test suite expansion (49 → 57 tests)
- `ApprovalsInboxPage.test.tsx`: tests render with task cards, empty state.
- `IncidentsPage.test.tsx`: tests list render, empty state, create dialog open.
- `InspectionsPage.test.tsx`: tests list render, empty state, create dialog open.
- All new tests use `vi.hoisted()` pattern consistent with existing suite.

## Remaining gaps to full v1 depth

These are not blockers for the current integration milestone, but are the highest-value next increments.

1. Deep workflow actions on operational pages
- Edit/delete flows for incidents and inspections (detail modals or dedicated pages).
- Missing optimistic updates and mutation-level validation messages in some sections.

2. Advanced filtering and pagination
- Current pages mostly use basic filters and static limits; server pagination controls and saved filters are not uniformly implemented.

3. Drill-down navigation
- Most operational registries are list-first pages; deep details pages and cross-links (incident -> logs, inspection -> result artifacts) should be expanded.

4. Unified table abstraction
- Tables are currently consistent in style but still page-local in logic.
- Shared DataTable abstractions (sort/filter/persisted preferences) should be consolidated for maintainability.

5. E2E coverage for role/tenant scenarios
- Unit/component tests are present, but there is still a gap in end-to-end tests for:
  - cross-tenant isolation checks
  - role switching and no-access redirect behavior
  - full CRUD business workflows

## Risks and mitigations

1. Risk: backend contract drift on new endpoints
- Mitigation: keep DTO types aligned with OpenAPI snapshots and add contract tests for key payloads.

2. Risk: permission mismatch between backend and frontend aliases
- Mitigation: maintain explicit alias map and add tests for normalized role/permission resolution.

3. Risk: partially implemented action buttons can be interpreted as fully supported flows
- Mitigation: gate unfinished mutations behind feature flags or explicit UX labels in backlog phase.

## Recommended next sprint priorities

1. Implement full create/edit flows for incidents, inspections, training assignments, and warehouse operations.
2. Introduce shared server-side pagination/filter state helper for all major tables.
3. Add route-level e2e suite for tenant+RBAC regression coverage.
4. Add telemetry for action failures and retry visibility on mutation-heavy pages.

## Incremental update (current task)

- Fixed compile-time RBAC inconsistency: SideNav referenced permissions that were absent in the canonical permission registry (`GENERATION_VIEW`, `WAREHOUSE_VIEW`, `CRM_FINANCE_VIEW`, `INTEGRATIONS_VIEW`, `CLIENT_PORTAL_VIEW`).
- Added production routes and guarded screens for missing mandatory sections:
  - `/warehouse`
  - `/crm-finance`
  - `/integrations`
  - alias routes `/generation`, `/archive` (with preserved `/archive/search`).
- Expanded role catalog and alias normalization for tenant/business roles (`auditor_ro`, `client`, `methodist`, `project_manager`, etc.).
- Added ability test coverage for role/permission aliases for new modules.

### Remaining work after this increment

- Replace static table datasets in newly added pages with API-backed stores when backend contracts for CRM/finance and integrations health are finalized.
- Expand integration tests to validate route-level denial for all newly added permissions.
