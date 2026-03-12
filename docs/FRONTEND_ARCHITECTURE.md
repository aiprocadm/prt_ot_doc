# FRONTEND_ARCHITECTURE

## Goals

- Keep tenant-safe and permission-safe behavior as default.
- Isolate transport, domain API adapters, and UI concerns.
- Standardize route guards and operational page states (loading/error/empty).
- Enable incremental expansion to v1 without broad rewrites.

## High-level structure

Frontend is organized in layered modules:

1. App shell and routing
- Router composition and protected route enforcement.
- Layout split: auth area and main application area.

2. Security and access control
- Authentication store and session bootstrap.
- Tenant gate/check and tenant-aware API context.
- Permission + role model, ability builder, and route/action-level checks.

3. API layer
- Central HTTP client with auth/tenant handling.
- Domain-specific adapters in src/api for each business module.

4. Feature/page layer
- Page-level containers orchestrating query state.
- Shared visual states: LoadingScreen, ErrorState, EmptyState.
- Consistent table/card presentation components.

5. Shared primitives and utilities
- UI component kit and helper utilities (date formatting, className helpers, etc.).

## Core architectural decisions

1. Central API client
- All backend requests route through a shared apiClient.
- Domain modules expose typed methods and hide endpoint details from pages.

2. Permission-driven composition
- Route access is controlled by ProtectedRoute + permission constants.
- Navigation visibility is generated from the same permission source.

3. Role and permission normalization
- Ability layer supports aliases to handle naming variance from identity providers and backend role conventions.
- Effective permissions are computed from either explicit user permissions or role expansion.

4. Tenant-first behavior
- Security checks include scope checks (tenant/company/site/project/contractor when provided).
- Pages rely on guarded route entry and store initialization before interaction.

## Route and navigation architecture

- Router includes grouped route blocks by permission domain (documents, operations, reports, admin, integrations).
- Side navigation is sectioned by business capability and filtered by runtime ability.can(permission).
- Feature flags are used for selective visibility (example: EDO section visibility toggle).

## Data flow pattern on operational pages

Typical page flow:

1. Enter page through permission-guarded route.
2. Trigger load() on mount (often parallel requests via Promise.all).
3. Render:
- loading state while in flight
- error state with retry callback
- empty state when dataset is empty
- table/card views for loaded data
4. Provide explicit refresh action to re-fetch server state.

## Domain API modules introduced in this cycle

- ppe.ts: item registry, issues, expiring issues.
- training.ts: courses, expiring certificates.
- incidents.ts: incidents list, incident logs; **create() added in Cycle 2**.
- inspections.ts: inspections list, inspection results; **create() added in Cycle 2**.
- finance.ts: orders and invoices.
- integrations.ts: webhook endpoints, deliveries, outbox events, endpoint test action.

## Create/mutation flow pattern (Cycle 2)

Transactional create dialogs follow a consistent pattern across IncidentsPage and InspectionsPage:

1. A `Dialog` is triggered by a primary action `Button`.
2. Local `form` state is managed with `useState`.
3. On submit: `setCreating(true)`, call `api.create(form)`, show `toast.success()` or `toast.error()`.
4. On success: close dialog with `setCreateOpen(false)`, reload list with `void load()`.
5. Required fields are validated before submit; disabled state on submit button while `creating`.

Example stub to replicate for new pages:
```tsx
const [createOpen, setCreateOpen] = useState(false);
const [creating, setCreating] = useState(false);
// ...
const handleCreate = async () => {
  setCreating(true);
  try {
    await domainApi.create(form);
    toast.success("Запись создана");
    setCreateOpen(false);
    void load();
  } catch {
    toast.error("Ошибка при создании");
  } finally {
    setCreating(false);
  }
};
```

## Testing strategy in architecture

- Component/page tests for API-backed rendering and user actions.
- Mocked API modules to isolate UI behavior and error handling.
- Role/permission path verification through targeted routing and ability tests (existing and planned).

## Known architectural trade-offs

1. Page-level fetch orchestration is duplicated across some modules.
- Trade-off accepted for velocity during v1 section completion.
- Planned: reusable query helpers/composables for list pages.

2. Table behaviors are mostly page-local.
- Planned: shared DataTable behavior for sorting/pagination/filter state persistence.

3. Some mutation paths are still backlog items.
- Read-heavy operational visibility is implemented first.
- Planned: complete transactional create/edit flows with stronger validation.

## Update: RBAC + route normalization for missing v1 sections

- Permission model is now the single source of truth for both navigation and route guards, including v1 business domains:
  - `generation.view`
  - `warehouse.view`
  - `crm_finance.view`
  - `integrations.view`
  - `client_portal.view`
- Route zones extended with dedicated guarded routes for Warehouse, CRM/Finance, and Integrations modules.
- Role normalization enhanced with alias map in ability layer to support heterogeneous backend role naming.
