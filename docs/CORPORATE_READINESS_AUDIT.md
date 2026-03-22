# Corporate Readiness Audit

_Date:_ 2026-03-22

## Scope of this audit wave
- Verified repository runtime code before changing behavior.
- Focused this wave on factual enterprise-readiness assessment plus an incremental hardening of the PWA/mobile bootstrap seam.
- Kept all changes additive and backward-compatible; no large rewrite was performed.

## Confirmed production-usable foundations
The following contours are already usable as enterprise foundations, even though they still need consistency and operational hardening:
- Tenant resolution, tenant-scoped DB sessions, and token tenant checks are implemented in `backend/app/api/dependencies.py` and `backend/app/core/security.py`.
- Approval/sign/EDO, document generation, packs, dashboards, inspections, incidents, training, PPE, files, and admin slices all have runtime routes and frontend screens wired into the main app shell.
- `frontend/vite.config.ts` already contains a real `VitePWA` plugin setup plus Workbox runtime caching; this is a practical baseline rather than a fully field-ready offline contour.
- `backend/app/api/routes/integration_readiness.py` already exposes a tenant-scoped readiness API that separates configured providers from contract-only placeholders.

## Confirmed foundation-level / partial operational areas
These areas exist and are useful, but are not yet at a fully hardened corporate rollout level:
- Many frontend pages are operational but remain registry-style pages or thin projection wrappers rather than fully scenario-first workspaces.
- Operational workspace capabilities (attention center, readiness blockers, deep-linked action inboxes, recent drafts, recommendation blocks) are still partial and distributed.
- PWA/offline exists as installable shell + sync endpoints, but not yet as a complete field-ready workflow contour.
- Document core is strong, but readiness, dependency mapping, deterministic snapshot visibility, and cross-stage lifecycle observability remain incomplete.

## Confirmed stub / mock / deferred areas
The following facts were re-verified directly in runtime code and remain important blockers for corporate rollout:
- `backend/app/api/routes/ws_stub.py` — WebSocket route remains explicitly deferred and returns stub semantics.
- `backend/app/celery/tasks/document_jobs_required.py` — compatibility wrappers exist and some bridges are real, but deferred/stub compatibility envelopes still remain for selected jobs when runtime handlers are not configured.
- `backend/app/services/pipeline_step_handlers.py` — pipeline orchestration split has started, but deferred stages still remain in the broader pipeline execution contour.
- `backend/app/services/integrations/stubs.py` — stub providers still back 1C / EDO / FRDO / EISOT non-production behavior.
- `backend/app/api/routes/approval_signing_v1.py` — default signing provider path still uses non-production provider semantics by default.
- `backend/app/api/routes/approval_orchestration.py` — mock provider path still exists.
- `backend/app/api/routes/edo_workflow.py` — API still contains mock/stub workflow semantics.
- `/api/pwa/bootstrap` previously returned a simplified payload with `current_user.id = None`, empty route permissions, and empty dictionaries; this wave hardens it, but the wider offline queue/conflict UX remains unfinished.

## Frontend operational status
### Operational enough for daily use, but still uneven
- Dashboards, documents, packs, approvals, EDO, incidents, inspections, contractors, settings, reference, medical, admin, files, reports, and tasks all have routable frontend screens.
- Shared UI primitives for loading/error/empty states exist (`EmptyState`, `ErrorState`, `LoadingScreen`, permission components), which is a strong base for consistency work.

### Still thin / partial / wrapper-like in enterprise terms
- Role-based workspaces are not yet the dominant navigation model.
- Attention center and readiness blocker UX are not unified across modules.
- Critical operational actions are still spread across module-specific pages instead of flowing through a common work inbox.
- Offline/mobile flows still lack a complete queue state UI, conflict resolution workflow, and durable drafts/resume UX.

## Backend consistency findings
### What is already strong
- Tenant-aware sessions are injected centrally.
- RBAC/ABAC helpers exist and enforce tenant/company/site/document/risk constraints.
- Request context wiring stores current user and tenant data for downstream services and logging.

### What still lacks platform-wide consistency
- Not every business route has been audited endpoint-by-endpoint for consistent tenant, authz, audit, and structured error behavior.
- Sensitive actions are not yet normalized into one enterprise audit contract across all modules.
- Correlation-id propagation is present in parts of the platform, but not yet normalized end-to-end for every route and background chain.
- Background jobs still need a full consistency review to verify tenant propagation, retries, dead-letter semantics, and diagnostics across all job families.

## Architecture debt and duplication
Confirmed structural debt still relevant for enterprise hardening:
- Fat files remain, especially `backend/app/api/v1/router.py`, `backend/app/models/models.py`, `backend/app/services/pipelines_orchestrator.py`, `backend/app/tasks.py`, `backend/app/api/routes/approval_signing_v1.py`, and `backend/app/api/routes/edo_workflow.py`.
- Legacy/parallel structures still coexist in router composition, models, and task entrypoints.
- Approval, signing, and EDO remain split across parallel route families that need canonical consolidation without breaking compatibility.

## Enterprise rollout blockers
### Highest priority blockers
1. Full consistency pass for tenant/authz/audit/correlation behavior.
2. Clear separation of production-grade internal orchestration vs explicit stub/mock adapters.
3. Operational workspace layer: attention center, task inbox, readiness blockers, recent drafts, recommendations, and deep-linking.
4. Data quality/readiness blocker layer for core entities.
5. PWA/mobile hardening beyond installability: queue state, retry/resume, conflict handling, drafts, media sync.
6. Admin/governance diagnostics for tenant readiness, providers, jobs, and environment state.

## What this wave actually hardened
- `/api/pwa/bootstrap` now returns authenticated current user projection, route permission projections, offline dictionaries, sync-state counters, and explicit diagnostics instead of a simplified anonymous payload.
- Existing documented stub/mock/deferred seams were refreshed into the new corporate-readiness documentation set so the next wave can continue without external memory.
