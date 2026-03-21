# Frontend Static to Real Map

_Date:_ 2026-03-21

## Converted in this pass

### CRM / Финансы
- Route: `/crm-finance`
- Previous state: hardcoded `deals` array rendered directly in `frontend/src/pages/crm-finance/CrmFinancePage.tsx`.
- Current state: real tenant-scoped data flow using existing backend APIs:
  - `GET /contracts`
  - `GET /orders`
  - `GET /invoices`
  - `GET /billing/plan` (best-effort for contextual billing status/plan badge)
- UI hardening added:
  - loading state
  - error state with retry
  - empty state
  - local search over contract/client/order/invoice identifiers
  - summary KPI cards derived from actual returned entities
- Notes on maturity:
  - The page is now operationally backed by real data, but it still projects CRM/finance through contracts/orders/invoices rather than a dedicated deals pipeline.
  - This is an honest V1 improvement, not a claim of full CRM maturity.

## Confirmed remaining candidates for future conversion
- `/warehouse`
- inspection prep and audit prep screens
- several dashboard variants that still need richer live projections
- additional registry/settings/reference screens already noted in repo audit docs

### PPE / Warehouse / Prescriptions / Findings / Corrective Actions / Audit Prep
- Routes: `/ppe`, `/warehouse`, `/prescriptions`, `/findings`, `/corrective-actions`, `/audit-prep`
- Previous state:
  - `/warehouse` rendered hardcoded stock rows.
  - `/ppe` rendered hardcoded employee PPE cards.
  - `/prescriptions` was effectively a title-only stub.
  - `/findings` rendered a local three-row demo table.
  - `/corrective-actions` rendered a local CAPA array.
  - `/audit-prep` rendered a static package table.
- Current state:
  - `/warehouse` now uses `GET /ppe/items` + `GET /ppe/issues/expiring`.
  - `/ppe` now uses `GET /ppe/issues`, `GET /ppe/items`, and `GET /persons`.
  - `/prescriptions` now uses `GET /prescriptions`.
  - `/findings` now uses `GET /findings`.
  - `/corrective-actions` now uses `GET /corrective-actions`.
  - `/audit-prep` now builds a real projection from `GET /inspections`, `GET /prescriptions`, and overdue `GET /tasks`.
- UI hardening added:
  - loading / error / empty states
  - query filtering where useful
  - real status / severity / due-date / effectiveness projections where available
  - KPI cards derived from live tenant data rather than showcase arrays
- Honest maturity note:
  - `audit-prep` is now *real-data-backed*, but still uses a lightweight derived projection rather than a dedicated backend readiness engine.
  - `findings` and `corrective-actions` are now operational registries, but still need richer linked-entity cards/timeline/task orchestration in future waves.

