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
