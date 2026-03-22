# FRONTEND

## Canonical frontend root
`frontend/`

## Core runtime files
- `package.json`
- `vite.config.ts`
- `src/main.tsx`
- `src/router/AppRouter.tsx`

## Canonical frontend layering
- `src/router/` — route composition, shell wiring, protected navigation.
- `src/pages/` — feature screens and workflow-specific operator views.
- `src/components/` — reusable enterprise UI building blocks.
- `src/stores/` — persisted UI state, including document wizard continuity.
- `src/__tests__/` — route, screen, and shared client-side regression coverage.

## Document-core screens
- `/documents/branding` — organization/site branding settings, preview history, server-side branded generation history, reproducibility snapshot.
- `/documents/wizard` — step-based wizard for template selection, batch generation and branded preview before generation.
- `/admin/layout-presets` — CRUD/editor for layout presets.

## Branding UX in this wave
Wizard step 5 now supports:
- selecting organization and optional branch/site;
- selecting layout preset or using profile default;
- running live branded preview via backend branding API;
- showing the effective source chain and branch-level branded name that will be injected into headers;
- reading reproducibility metadata before generation;
- retaining short preview history in UI state.

Branding settings now expose separate `Header requisites` and `Footer requisites` fields, matching the backend profile shape used by the document core.


## Static-to-real conversion updates
- `/crm-finance` now uses live tenant-scoped `/contracts`, `/orders`, `/invoices`, and `/billing/plan` API calls instead of a hardcoded demo deals table.
- The page now exposes loading, error, empty, and local-search states while keeping the existing route and permission contract unchanged.

## 2026-03-21 operational page maturity update
- `/crm-finance`, `/warehouse`, `/ppe`, `/prescriptions`, `/findings`, `/corrective-actions`, `/audit-prep`, and the dashboard inner tabs now use real backend data flows rather than local demo arrays/stubs.
- The preferred frontend pattern remains: `src/api/*` wrapper -> page-level loading/error/empty states -> shared table/card shell components.
- Dashboard tabs specifically now consume `GET /dashboard/summary` + `GET /dashboard/operational` through `src/stores/dashboard.ts`, so future Attention Center expansion can enrich one backend projection contract instead of reintroducing page-local ad hoc arrays.
- Pages still awaiting similar treatment include fire safety pages, activities/CAPA overview aggregations, and inspection-prep showcase screens.

## 2026-03-22 note
- This wave did change frontend platform behavior additively: `frontend/vite.config.ts` now uses `vite-plugin-pwa`, and `frontend/src/main.tsx` registers the generated service worker through `frontend/src/pwa/register.ts`.
- The platform now has a real installable PWA baseline: manifest generation, service worker generation, runtime registration, and cache rules for shell/static/API-read traffic.
- This is still only a baseline. The super-TZ gaps remain open for tenant-aware offline queues, sync/conflict UX, media lifecycle handling, stronger `/pwa/bootstrap`, and hardened `/pwa/sync/*` semantics.
