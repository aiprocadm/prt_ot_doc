# Corporate Readiness Plan

_Date:_ 2026-03-23

## Guardrails
1. Do not delete or destabilize working features for architecture purity.
2. Do not do a massive rewrite.
3. Every new or hardened flow must remain tenant-aware, permission-aware, audited, and testable.
4. Non-production stub/mock behavior must stay explicit in API behavior, diagnostics, and docs.
5. Document every decision in-repo so the next wave does not rely on external memory.

## Recommended execution order
1. Consistency hardening.
2. Operational workspace layer.
3. Document core centralization/strengthening.
4. Remove corporate-blocking stubs.
5. Data quality + readiness blockers.
6. Mobile/PWA practical hardening.
7. Admin/governance/diagnostics.
8. Reliability/observability/runbooks.
9. Final UX cleanup and tests.

## Phase-by-phase plan
### Phase A — factual corporate-readiness audit
- Keep `docs/CORPORATE_READINESS_AUDIT.md` and `docs/CORPORATE_READINESS_PLAN.md` aligned to actual runtime facts.
- Re-verify deferred/mock/stub seams directly from code before claiming readiness.
- Maintain an explicit split between production-usable foundations, foundation-level areas, and remaining blockers.

### Phase B — enterprise consistency hardening
#### Backend
- Verify tenant context on every business route family.
- Normalize permission checks for read/write/bulk/export/search.
- Normalize structured error contracts.
- Normalize correlation-id propagation.
- Normalize audit for sensitive actions.
- Verify background jobs preserve tenant context and diagnostics.

#### Frontend
- Enforce route-level permission awareness.
- Enforce action-level permission awareness and hide unavailable controls.
- Standardize loading/error/empty states.
- Add consistent unsaved-changes protection for critical forms and wizards.

### Phase C — operational workspace layer
- Add role-based workspaces.
- Add attention center.
- Add task inbox.
- Add readiness blockers.
- Add recent drafts / recent items.
- Add recommendation blocks.
- Add deep-linking from dashboards to action screens.
- Standardize entity cards with summary, tabs, timeline, tasks, files, and audit.

### Phase D — document core to central engine
- Strengthen the full lifecycle from template through archive without rewriting the existing core.
- Add scope-aware template resolution across system / tenant / company / site.
- Finalize readiness scores with reasons and recommended actions.
- Add dependency-map foundations linking NPA, templates, packages, routes, and rules.
- Persist render snapshots and deterministic metadata.
- Harden rerun idempotency and progress semantics.
- Ensure document passport completeness and reproducibility.

### Phase E — remove corporate-blocking stubs
- Isolate stub/mock providers cleanly from production-grade orchestration.
- Make provider mode explicit in API responses, docs, and diagnostics.
- Replace avoidable deferred/stub behavior with real internal logic where possible.
- Keep provider contracts stable for future certified adapters.
- Prioritize approval/sign orchestration, EDO workflow orchestration, pipeline execution, document jobs reporting, and integration readiness diagnostics.

### Phase F — mobile / PWA / offline hardening
- Keep the existing PWA plugin and runtime caching.
- Build on the hardened `/api/pwa/bootstrap` contract.
- Add frontend offline queue model.
- Add sync state UI.
- Add conflict-resolution UX.
- Add durable drafts persistence.
- Add retry/resume semantics.
- Cover selected field scenarios: briefings, incident drafts, checklist drafts, task/comment capture, media sync, and training acknowledgement.

### Phase G — data quality + readiness blockers
- Detect incomplete entities, missing relations, expired critical data, and feasible duplicates/conflicts.
- Persist issues and expose severity plus scenario impact.
- Integrate blockers into document readiness, contractor readiness, employee readiness, dashboards, and the attention center.
- Start with employees, companies/sites, templates/documents, training, PPE, and contractors.

### Phase H — UI/UX hardening
- Convert partial/static/thin pages into real operational screens.
- Unify registries, entity cards, and forms.
- Add smart empty states and contextual hints.
- Reduce clutter and move rare controls to secondary actions.
- Enforce progressive disclosure.
- Prioritize contractors, reference, settings, medical, fire safety/training/inspections, inspection plans/prep/checklists, admin, dashboards, and client portal views.

### Phase I — enterprise admin / governance / diagnostics
- Turn admin into a true operational console.
- Add tenant settings, feature/module visibility, integration readiness, jobs diagnostics, data-quality overview, billing/usage diagnostics, environment diagnostics, provider-mode diagnostics, and tenant startup readiness.

### Phase J — reliability / observability / runbooks
- Normalize retries, poison handling, job heartbeat/watchdog, failed-job diagnostics, cleanup tasks, integrity checks, and health/readiness coverage.
- Update `docs/SETUP.md`, `docs/TESTING.md`, `docs/OBSERVABILITY.md`, `docs/RUNBOOK.md`, and `docs/RELEASE_READINESS.md` as each reliability wave lands.
- Keep local bootstrap and CI verification reproducible.

### Phase K — tests and acceptance
- Add/update backend unit and integration tests after each major wave.
- Add/update frontend tests for operational pages and offline/mobile behavior.
- Prioritize tenant isolation, authz, document lifecycle, readiness score, data-quality blockers, task/attention projections, workflow/sign/EDO orchestration, offline edge cases, and converted operational screens.

## This wave outcome
- Completed the corporate-readiness audit refresh.
- Kept the roadmap explicitly centered on depth hardening rather than breadth expansion.
- Established the hardened PWA bootstrap seam as an enabling dependency for the mobile/offline wave.

## Success criteria for the next implementation wave
- A logged-in user immediately sees what requires attention, what is overdue, what is blocked, and what to do next.
- Routes and actions behave consistently across modules for tenancy, permissions, errors, and audit.
- Provider mode is explicit and impossible to mistake for production readiness.
- Mobile/offline work uses real bootstrap projections instead of placeholder state.
