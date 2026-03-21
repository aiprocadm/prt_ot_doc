# CODEX Wave Audit

_Date:_ 2026-03-21

## Canonical entrypoints
- Backend ASGI/bootstrap: `backend/app/main.py` and `backend/app/api/app.py`.
- Backend v1 composition root: `backend/app/api/v1/router.py`.
- Worker bootstrap: `backend/app/worker.py`.
- Frontend browser bootstrap: `frontend/src/main.tsx` -> `frontend/src/App.tsx` -> `frontend/src/router/AppRouter.tsx`.

## Active roots
- Backend active roots: `backend/app/api`, `backend/app/modules`, `backend/app/services`, `backend/app/models`, `backend/app/schemas`, `backend/app/domains`.
- Frontend active roots: `frontend/src/pages`, `frontend/src/components`, `frontend/src/api`, `frontend/src/stores`, `frontend/src/router`.
- Documentation roots used as source of truth for this wave: `docs`, `docs/audit`, `docs/ADR`, `GAP_REPORT.md`, `KNOWN_LIMITATIONS.md`, `ACCEPTANCE_TEST_MATRIX.md`.

## Migration head baseline
- Alembic configuration is active at `backend/app/migrations/alembic.ini` and revisions live under `backend/app/migrations/versions`.
- This wave intentionally avoided schema changes; migration head remains unchanged and therefore backwards-compatible by design.

## Active router/module map
- The backend router surface remains broad and tenant-scoped. Major active groups include auth, admin/authz, audit, dashboard, companies/persons, inspections/incidents/prescriptions, PPE, documents/templates/branding/replace/pdf/pipelines, tasks/workflow, outbox/webhooks, client portal, billing, analytics, reports, and PWA sync.
- This wave introduced `backend/app/api/v1/route_groups.py` as a compatibility-safe registry layer so `backend/app/api/v1/router.py` stops owning the entire `include_router(...)` topology directly.

## Frontend route map baseline
- Canonical browser entry remains `frontend/src/router/AppRouter.tsx`, but permission-aware route groupings now live in `frontend/src/router/routeGroups.tsx` and lazy page ownership lives in `frontend/src/router/pageRegistry.tsx`.
- Route inventory still covers dashboards, registries, document core, approvals, search/archive, operational safety modules, client portal, CRM/finance, integrations, and admin surfaces.
- `AppRouter.tsx` is now a thinner bootstrap shell; future decomposition can proceed cluster-by-cluster without reopening the full route monolith.

## Static / stub page map
Confirmed static or mostly placeholder pages from direct code audit before/around this pass:
- `frontend/src/pages/warehouse/WarehousePage.tsx` — static stock rows.
- `frontend/src/pages/ppe/PpePage.tsx` — static PPE card rows and KPI cards.
- `frontend/src/pages/prescriptions/PrescriptionsPage.tsx` — title-only stub.
- `frontend/src/pages/audit-prep/AuditPrepPage.tsx` — static package table.
- Still placeholder/foundation after this pass: several fire-safety pages, parts of dashboard tabs, reference/settings/admin showcase blocks, activities/CAPA overview, and inspection-prep package screen.

## Stub / mock / deferred integrations map
- WebSocket remains explicitly deferred: `backend/app/api/routes/ws_stub.py` returns HTTP 501.
- Approval/sign routes still support explicit `stub` providers for non-certified signature flows.
- Integration readiness and external provider layers still contain documented placeholder/stub contracts for future certified adapters.
- PWA/offline remains foundation-level; the repo has `/pwa/*` backend contracts but not yet a mature frontend offline queue/service-worker package.

## TODO / deferred map
- Full decomposition of `backend/app/models/models.py` into true bounded modules is still pending.
- Dashboard inner tabs still mix real summary data with placeholder projections.
- Attention center/data quality/PWA maturity/workflow SLA hardening remain next-wave work.
- Realtime UX is still deferred to a future phase; current supported path is REST + polling.

## Acceptance coverage baseline
- Backend already contains broad tests for tenancy, billing, approvals, search, pipelines, incidents/inspections/CAPA prep, notifications, replace, files, portal, and workflow surfaces.
- Frontend already contains smoke/permission/store tests for dashboards, documents, portal, tasks, CRM/finance, routes, and API client behavior.
- This wave adds focused frontend coverage for newly-realized operational pages (`warehouse`, `prescriptions`, `findings`, `corrective-actions`, `audit-prep`).

## Repo duplication / legacy map
- `backend/app/models/models.py` remains the mega-model compatibility module; new canonical imports in this wave start using narrower compatibility layers (`backend/app/models/tenanting.py`, `backend/app/models/ppe_registry.py`).
- `backend/app/modules/approval` vs `backend/app/modules/approvals` remains a red-flag naming split; keep singular as legacy compatibility and prefer plural for active approval API flows.
- `docs/ADR` vs `docs/adr` remains a documentation canonicalization risk; new ADRs in this wave are placed under `docs/ADR`.

## Fat files requiring decomposition
- `backend/app/api/v1/router.py` — still fat, but router registration has now been pulled behind a registry layer.
- `backend/app/models/models.py` — ~3k LOC mega-model and the highest persistence-compatibility risk.
- `frontend/src/router/AppRouter.tsx` — still the canonical shell, but materially slimmer after route-cluster extraction; future work should evolve `routeGroups.tsx` clusters rather than re-growing `AppRouter.tsx`.
- `frontend/src/pages/dashboard/DashboardPage.tsx` — still mixes real KPI summary with static inner-tab projections.

## Incomplete super-TZ areas still visible
- Universal task/attention/timeline is partial.
- Data Quality Center is not yet implemented as a dedicated persisted layer.
- PWA/offline maturity is not yet production-grade.
- Workflow/sign/EDO providers remain partially mocked.
- Several frontend registries still need conversion from showcase mode to real projections.

## Risky compatibility areas
- `backend/app/api/v1/router.py` must continue to preserve existing path contracts; only registry extraction or compatibility imports are safe.
- `backend/app/models/models.py` cannot be split by moving SQLAlchemy table declarations abruptly without carefully preserving Alembic import paths.
- PPE/inspection/prescription pages depend on manager/admin read permissions; UI conversion to real data now surfaces real authz behavior and must not be mistaken for anonymous showcase access.

## What changed from static/stub to real in this wave
- `warehouse` now reads real tenant-scoped PPE catalog + expiring-issue data from `/ppe/items` and `/ppe/issues/expiring`.
- `ppe` now reads real issuance history and person context from `/ppe/issues`, `/ppe/items`, and `/persons`.
- `prescriptions` now renders a real registry backed by `/prescriptions`.
- `findings` now renders a real registry backed by `/findings`.
- `corrective-actions` now renders a real registry backed by `/corrective-actions`.
- `audit-prep` now derives package/readiness-like projections from `/inspections`, `/prescriptions`, and overdue `/tasks` instead of static rows.

## Additional hardening completed in this pass
- Frontend operational registries now share a consistent async loading hook (`frontend/src/hooks/useAsyncResource.ts`) and local pagination/search state (`frontend/src/hooks/useLocalRegistry.ts`) instead of page-local ad hoc loading code.
- Findings, corrective actions, and prescriptions now use the shared registry table shell with search + pagination while preserving the same route/UI meaning.
- Frontend route composition now also follows a shared pattern: `frontend/src/router/pageRegistry.tsx` centralizes lazy page loaders and `frontend/src/router/routeGroups.tsx` centralizes permission-aware route clusters.
- Backend progressive model decomposition now also exposes `backend/app/models/document_core.py` so document pipeline/template imports can move away from `app.models.models` incrementally without changing table ownership.
