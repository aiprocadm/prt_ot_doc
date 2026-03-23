# Corporate Readiness Plan

Date: 2026-03-23

## Guardrails
1. Do not remove working features for architecture purity.
2. No massive rewrite.
3. Every change must be tenant-aware, permission-aware, auditable, and tested.
4. Stub/mock/deferred behavior must be explicit in API/docs/admin diagnostics.
5. All decisions and gaps must be captured in repo docs.

## Priority order (approved)
1. Consistency hardening.
2. Operational workspace layer.
3. Document core centralization.
4. Remove corporate-blocking stubs.
5. Data quality and readiness blockers.
6. Mobile/PWA practical hardening.
7. Admin/governance/diagnostics.
8. Reliability/observability/runbooks.
9. Final UX cleanup and tests.

## Phase plan and DoD
### Phase A: Factual corporate-readiness audit
Scope:
- Keep audit and plan documents synchronized with runtime code.
- Reconfirm mandatory stub/mock/deferred facts.
- Classify modules as production-usable vs foundation-only.

Definition of done:
- docs/CORPORATE_READINESS_AUDIT.md is fact-checked.
- docs/CORPORATE_READINESS_PLAN.md includes ordered execution and measurable outcomes.

### Phase B: Enterprise consistency hardening
Backend:
- Verify tenant checks on business endpoints.
- Normalize permission checks on read/write/bulk/export/search.
- Normalize structured errors and correlation-id.
- Normalize audit for sensitive actions.
- Ensure background jobs preserve tenant context.

Frontend:
- Route-level and action-level permission awareness.
- Hide unavailable actions.
- Standard loading/error/empty patterns.
- Unsaved-changes protection in critical forms and wizards.

Definition of done:
- Consistency checklist applied to all prioritized route families.
- Regression tests added for tenant/authz/error shape.

Current progress (this iteration):
- Started route-family consistency execution in PWA sync endpoints by enforcing user ownership and server-controlled mutable fields.
- Added focused regression tests for anti-spoofing and owner access in offline endpoints.

### Phase C: Operational workspace layer
Deliver:
- Role-based workspace surfaces.
- Attention center.
- Task inbox.
- Readiness blockers with reasons and recommended actions.
- Recent drafts/recent items/recommendation blocks.
- Dashboard deep links to action screens.
- Consistent entity cards (summary, timeline, tasks, files, audit).

Definition of done:
- User can answer immediately: what is overdue, blocked, urgent, and next action.

### Phase D: Document core central engine (no rewrite)
Deliver:
- Unified lifecycle: template -> readiness -> branding -> replace -> PDF -> approval -> sign -> EDO -> archive.
- Scope resolution hardening: system/tenant/company/site.
- Readiness score with explainable reasons and actions.
- Dependency map foundations: NPA -> template -> package -> approval route -> rule.
- Deterministic render snapshots and metadata.
- Idempotent rerun and progress contracts.
- Complete reproducible document passport.

Definition of done:
- Existing document capabilities are not broken.
- Lifecycle status is reproducible and explainable.

### Phase E: Remove corporate-blocking stubs
Deliver:
- Separate internal production orchestration from non-production adapters.
- Explicit mode visibility: production/mock/stub.
- Replace avoidable deferred responses with real internal logic where feasible.
- Keep provider contracts stable.

Priority paths:
- approval/sign orchestration,
- EDO workflow,
- pipeline step execution,
- document jobs reporting,
- integration readiness diagnostics.

### Phase F: Mobile/PWA practical field readiness v1
Deliver:
- Keep existing /api/pwa/bootstrap foundation and harden it for field usage.
- Enrich permissions and dictionaries where scenario coverage is still shallow.
- Offline queue model on frontend.
- Sync-state UI.
- Conflict-resolution UI.
- Draft persistence, retry/resume.
- Field scenarios: briefing mark, incident draft, checklist draft, task/comment capture, media sync, selected training acknowledgement.

### Phase G: Data quality and readiness blockers
Deliver:
- Detect missing fields/relations, expirations, duplicates/conflicts (where feasible).
- Persist issues with severity and scenario impact.
- Integrate blockers into readiness surfaces and attention center.

Coverage minimum:
- employees,
- companies/sites,
- templates/documents,
- training,
- PPE,
- contractors.

### Phase H: UI/UX hardening
Deliver:
- Convert thin/partial pages to operational screens.
- Unify registries/entity cards/forms.
- Smart empty states and contextual hints.
- Reduce clutter and enforce progressive disclosure.

Priority pages:
- contractors,
- reference,
- settings,
- medical,
- fire safety/training/inspections,
- inspection checklists/plans/prep,
- admin,
- dashboards,
- client portal operational views.

### Phase I: Admin/governance/diagnostics
Deliver:
- Operational admin console.
- Tenant settings.
- Feature/module visibility.
- Integration readiness and provider mode diagnostics.
- Queue/job diagnostics.
- Data quality overview.
- Usage/billing diagnostics.
- Environment diagnostics.
- Tenant startup checklist.

### Phase J: Reliability/observability/runbooks
Deliver:
- Retry and DLQ/poison consistency.
- Watchdog/heartbeat.
- Failed-job diagnostics.
- Cleanup and integrity checks.
- Better readiness/health coverage.
- Reproducible local bootstrap and CI path.

Docs to update in this phase:
- docs/SETUP.md
- docs/TESTING.md
- docs/OBSERVABILITY.md
- docs/RUNBOOK.md
- docs/RELEASE_READINESS.md

### Phase K: Tests and acceptance
After each major wave:
- backend unit/integration tests,
- frontend tests,
- meaningful scenario coverage.

Priority test domains:
- tenant isolation,
- authz,
- document lifecycle,
- readiness score,
- data quality blockers,
- task/attention projections,
- workflow/sign/EDO orchestration,
- offline sync edge cases,
- converted operational pages.

## Deliverables for this planning wave
- docs/CORPORATE_READINESS_AUDIT.md
- docs/CORPORATE_READINESS_PLAN.md
- docs/CORPORATE_READINESS_COMPLETION_REPORT.md
- docs/CORPORATE_READINESS_REMAINING_GAPS.md
- docs/CORPORATE_READINESS_NEXT_STEPS.md

## Governance and change control
1. No massive rewrite or removal of working features.
2. Every new business path must remain tenant-aware, permission-aware and audited.
3. Any remaining stub/mock/deferred behavior must be explicit in API and diagnostics.
4. Every wave ends with docs update plus focused test evidence.
