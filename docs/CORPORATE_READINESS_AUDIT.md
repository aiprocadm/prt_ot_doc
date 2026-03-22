# Corporate Readiness Audit

_Date:_ 2026-03-22

## Scope and audit method
- Re-validated runtime code before treating any capability as enterprise-ready.
- Kept the assessment focused on whether the platform can be operated as a real corporate solution: tenant-safe, permission-safe, auditable, operationally usable, and explicit about non-production gaps.
- Did not assume the final super-spec was already implemented; compared the requested target shape against the current backend routes, services, tasks, and frontend runtime shell.

## Executive summary
The repository is already a strong enterprise platform foundation. It has real tenancy, broad module coverage, document-core depth, installable PWA infrastructure, and many operational screens. However, it is not yet uniformly production-grade at the platform level.

The biggest remaining blockers are not missing modules in breadth; they are consistency and operational maturity in depth:
- platform-wide tenant/authz/audit/correlation consistency;
- role-based workspace UX and action-oriented work queues;
- removal or explicit isolation of stub/mock/deferred provider behavior;
- data-quality and readiness blockers as persisted first-class entities;
- mobile/PWA field usability beyond installability;
- admin diagnostics and runbooks suitable for enterprise rollout.

## Confirmed production-usable foundations
The following areas are already strong enough to be treated as production-capable foundations rather than prototypes:
- Tenant context, tenant-scoped sessions, and tenant-aware security dependencies are implemented centrally in `backend/app/api/dependencies.py`, `backend/app/core/security.py`, `backend/app/core/tenant.py`, and related tenancy helpers.
- The document core already supports template upload, versioning, preview, replacement, branding, PDF generation, pack generation, and related lifecycle slices. This contour should be strengthened, not rewritten.
- Business modules are broad and real: documents, packs, approvals, EDO, incidents, inspections, training, PPE, files, billing, CRM/portal slices, and admin/diagnostics routes are all present in runtime code.
- `frontend/vite.config.ts` already contains a real `VitePWA` plugin setup with runtime caching. This is a meaningful field-readiness base, not just a placeholder manifest.
- `/api/pwa/bootstrap` is no longer anonymous/simplified in the current code path; `backend/app/api/routes/pwa_sync.py` now exposes authenticated current-user projection, route-permission projections, dictionaries, sync counters, and diagnostics that can support the next offline/mobile wave.

## Confirmed foundation-level / partial operational areas
These areas are valuable and usable, but are not yet at the standard required for a broad corporate rollout:
- Many frontend pages are operational registries or detail views, but not yet consistently converted into scenario-first workspaces.
- Shared components for loading/error/empty states exist, but they are not yet enforced uniformly across all high-value screens and wizards.
- Deep-linking from dashboards to action screens exists in places, but not yet as a universal operational pattern across modules.
- Entity representations are uneven: some areas behave like operational cards, while others remain partial pages or thin wrappers around existing APIs.
- Background jobs, retries, and diagnostics are present, but not yet normalized into one platform-wide enterprise reliability contract.

## Confirmed stub / mock / deferred facts
The following facts were re-verified directly from runtime code and remain material enterprise blockers until isolated or replaced:
- `backend/app/api/routes/ws_stub.py` — WebSocket events remain explicitly deferred and return `501 Not Implemented` with a deferred-to-P2 message.
- `backend/app/celery/tasks/document_jobs_required.py` — compatibility wrappers preserve real orchestrator execution when available, but still return deferred compatibility envelopes for named bridges when no runtime bridge is configured.
- `backend/app/services/pipeline_step_handlers.py` — some pipeline steps are real, but EDO-disabled paths still resolve to deferred status, so deferred stage behavior has not been eliminated from the wider pipeline contour.
- `backend/app/services/integrations/stubs.py` — explicit stub/disabled providers still exist for 1C, EDO, FRDO, and EISOT.
- `backend/app/api/routes/approval_signing_v1.py` — request models still default important provider fields to `stub`, so the default path is not production-safe by semantics.
- `backend/app/api/routes/approval_orchestration.py` — mock provider behavior still exists and must be isolated from production orchestration.
- `backend/app/api/routes/edo_workflow.py` — mock/stub semantics remain visible, including `provider_code="mock"` defaults and simulation-oriented behavior.
- `frontend/vite.config.ts` — PWA runtime caching is already in place and should be preserved.
- `/api/pwa/bootstrap` — the previous simplified bootstrap limitation is now partially addressed in code, but the wider mobile/offline contour still requires queue/conflict/draft UX and selected field workflows.

## Frontend operational assessment
### Production-usable or close to production-usable
- The application shell and route structure cover a wide business surface area and are not demo-only.
- Shared API clients and page modules exist for incidents, inspections, training, tasks, documents, approvals, EDO, billing, files, and other enterprise domains.
- Installable PWA packaging and cache strategy are already present.

### Still thin, partial, or inconsistent in enterprise terms
- Dashboards are not yet a single role-based operational workspace layer.
- Attention-center semantics are not yet unified into one user-facing inbox of overdue, blocked, assigned, and recommended actions.
- Readiness blockers are not yet exposed consistently across document, contractor, employee, and compliance scenarios.
- Critical forms and wizard-like screens still need a systematic unsaved-changes and resume/retry treatment.
- Client portal/admin/settings/reference contours remain functionally broad but still need stronger UX unification and progressive disclosure.

## Backend consistency assessment
### What is already strong
- Tenant record resolution and tenant-scoped session injection are centralized.
- RBAC/ABAC helpers exist and are already used in important places.
- The platform already carries request/user/tenant context through core helpers, which is a strong base for audit and tracing normalization.

### What is not yet consistent enough for enterprise rollout
- Not every business route family has been verified endpoint-by-endpoint for tenant enforcement across read, write, bulk, export, and search operations.
- Permission checks are not yet normalized into one obvious rule set across all route families.
- Structured error envelopes are uneven across endpoints; some paths return domain-specific responses while others still lean on raw HTTP exceptions.
- Correlation-id propagation exists but is not yet normalized across every synchronous and background execution path.
- Sensitive-action audit behavior is not yet confirmed as uniform across approvals, document lifecycle transitions, exports, integration actions, and admin operations.
- Background jobs preserve tenant context in important paths, but a platform-wide verification of retries, DLQ semantics, and diagnostics is still missing.

## Operational usability gaps
The repo still lacks several enterprise-operator essentials for day-to-day use:
- clear role-based workspaces;
- one attention center for overdue/blocked/assigned work;
- one task inbox spanning modules;
- readiness blockers with reasons and recommended actions;
- recent drafts/recent items panels;
- recommendation blocks grounded in actual readiness/data quality/workflow state;
- consistent entity cards with summary, tabs, timeline, tasks, files, and audit.

## Document-core-specific audit
The document core remains the strongest contour and should stay stable, but it still needs corporate-readiness strengthening:
- lifecycle unification across template -> readiness -> branding -> replace -> PDF -> approval -> sign -> EDO -> archive;
- stronger scope resolution for system / tenant / company / site template selection;
- document/package readiness score with reasons and recommended actions;
- dependency-map foundations linking NPA, template, package, route, and rules;
- deterministic render snapshots and reproducible metadata;
- idempotent rerun and progress semantics that are visible operationally;
- a complete reproducible document passport.

## Data-quality and readiness gaps
The current codebase does not yet expose a full persisted data-quality issue layer for:
- employees;
- companies and sites;
- templates and generated documents;
- training;
- PPE;
- contractors.

That means readiness currently depends too much on distributed checks and not enough on one persistent blocker model that can feed dashboards, entity cards, document readiness, and workspaces.

## Architecture debt and duplication
The repo still contains debt that matters operationally, even if it should be addressed incrementally rather than with a rewrite:
- fat files and parallel structures remain in `backend/app/api/v1/router.py`, `backend/app/models/models.py`, `backend/app/services/pipelines_orchestrator.py`, `backend/app/tasks.py`, `backend/app/api/routes/approval_signing_v1.py`, and `backend/app/api/routes/edo_workflow.py`;
- legacy and newer route families coexist in approvals/signing/EDO;
- compatibility wrappers are useful, but some still blur the line between production orchestration and non-production semantics.

## Enterprise rollout blockers
### Tier 1 blockers
1. Platform-wide consistency hardening for tenancy, authz, audit, correlation, and structured errors.
2. Role-based operational workspace layer with attention center, inbox, blockers, recent drafts, and deep links.
3. Clean separation of production orchestration from explicit stub/mock/deferred adapters.
4. Persisted data-quality and readiness blockers across core entities.
5. Mobile/PWA field usability: queue model, sync state, retry/resume, conflict handling, drafts, and field scenarios.
6. Operational admin/governance/diagnostics for provider modes, tenant readiness, jobs, and environment state.

### Tier 2 blockers
1. Deeper document-core lifecycle transparency and deterministic reproducibility.
2. Reliability consistency for retries, poison handling, watchdogs, and cleanup.
3. UX unification for overloaded pages, empty states, forms, and entity cards.

## What this wave actually accomplished
- Reframed the audit around factual corporate readiness, not generic backlog coverage.
- Preserved the documented evidence of the key deferred/mock/stub seams that still block a real enterprise rollout.
- Confirmed that the PWA base already has installability/runtime caching and that the `/api/pwa/bootstrap` seam has been strengthened enough to serve as a real projection API for the next mobile/offline wave.
