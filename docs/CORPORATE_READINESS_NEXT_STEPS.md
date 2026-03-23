# Corporate Readiness Next Steps

Date: 2026-03-23

## Wave 1 (start now): Consistency hardening
1. Build and apply a route-family checklist:
	- tenant enforcement,
	- permission checks (read/write/bulk/export/search),
	- structured error contracts,
	- correlation-id propagation,
	- sensitive-action audit.
2. Prioritize route families with highest business impact:
	- documents/packs,
	- approvals/sign/EDO,
	- incidents/inspections/training/PPE,
	- client portal,
	- admin diagnostics.
3. Add regression tests for tenant isolation and authz in each touched family.

Current delta completed in Wave 1:
- re-baselined factual enterprise-readiness audit and synchronized all 5 governance deliverables;
- fixed execution order and Definition of Done for phases B-K;
- preserved no-rewrite guardrails and explicit stub/mock/deferred transparency requirements;
- prepared targeted route-family and screen-family priorities for immediate execution;
- delivered first runtime consistency hardening slice for PWA sync owner scoping and anti-spoofing.

Current delta started in Wave 2:
- integrated attention center panel into dashboard with real workspace projections;
- added frontend test coverage for attention panel rendering and dashboard integration.
- connected dashboard task tab to workspace task-inbox projection with triage filters for overdue and priority views.
- started deep-linking from task inbox rows into action screen filters on TasksPage.
- added scenario-aware deep-linking from readiness blockers into concrete action modules.
- added recent items/drafts block to dashboard for faster return-to-work context.
- added entity-context navigation links in task inbox and recent task items.
- unified workspace navigation mapping to reduce route drift between dashboard, attention center and task registry.
- implemented first entity-card entry step: task links now transfer task/entity focus context and TasksPage shows focused context card with quick scenario actions.
- extended entity-card summary/timeline entry points for document, contractor and inspection contexts via query-driven focus cards.

Immediate next substep:
- execute endpoint-by-endpoint consistency sweep on approvals/sign/EDO and documents/packs route families (tenant/authz/error/audit/correlation) with focused regression tests.

Exit criteria:
- no route family exits wave without consistency checklist pass,
- test evidence for tenant/authz/error contract is added.

## Wave 2: Operational workspace layer
1. Expand role-based attention center and task inbox projections.
2. Add readiness blockers with severity, reasons, and recommended actions.
3. Add recent drafts/recent items and recommendation blocks.
4. Add deep links from dashboards to action screens.

Immediate next substep for Wave 2:
- deepen entity-card runtime behavior: add direct entity details loading, richer timeline events and cross-module action shortcuts from summary/timeline cards.

Exit criteria:
- user sees overdue/blocked/next actions immediately after login.

## Wave 3: Document core centralization
1. Unify lifecycle surface from template to archive.
2. Harden scope resolution (system/tenant/company/site).
3. Finalize readiness scoring with explainability.
4. Add deterministic render snapshots and document passport integrity.

Exit criteria:
- lifecycle is reproducible, explainable, and operationally visible.

## Wave 4: Remove corporate-blocking stubs
1. Separate production orchestration from stub/mock adapters.
2. Make non-production mode explicit in API and admin diagnostics.
3. Replace avoidable deferred responses with real internal logic.

Priority seams:
- approval_signing_v1,
- approval_orchestration,
- edo_workflow,
- pipeline_step_handlers,
- document_jobs_required,
- integrations/stubs.

## Wave 5: Data quality and readiness blockers
1. Persist issues for employees, companies/sites, templates/documents, training, PPE, contractors.
2. Integrate blockers into readiness, attention center, dashboards, and entity cards.

## Wave 6: Mobile/PWA practical hardening
1. Keep /api/pwa/bootstrap projection baseline and harden scenario depth for field workflows.
2. Implement frontend offline queue, sync-state UI, conflict UI.
3. Add retry/resume and robust drafts persistence.
4. Cover selected field scenarios.

## Wave 7: Admin/governance/diagnostics
1. Build operational admin console views for tenant readiness and provider modes.
2. Add queue/job diagnostics, data quality overview, usage/billing and environment diagnostics.

## Wave 8: Reliability/observability/runbooks
1. Normalize retry and DLQ/poison policies.
2. Add watchdog/heartbeat and failed job diagnostics.
3. Add cleanup/integrity checks.
4. Update setup/testing/observability/runbook/release-readiness docs.

## Wave 9: Final UX cleanup and tests
1. Convert priority thin pages to operational screens.
2. Unify forms/registries/entity cards and declutter overloaded pages.
3. Finalize acceptance tests for corporate scenarios.

## Priority pages for conversion
- frontend/src/pages/contractors/ContractorsPage.tsx
- frontend/src/pages/reference/ReferencePage.tsx
- frontend/src/pages/settings/SettingsPage.tsx
- frontend/src/pages/activities/ActivitiesPage.tsx
- frontend/src/pages/medical/MedicalPage.tsx
- frontend/src/pages/fire-safety/FireSafetyPage.tsx
- frontend/src/pages/fire-training/FireTrainingPage.tsx
- frontend/src/pages/fire-inspections/FireInspectionsPage.tsx
- frontend/src/pages/inspection-checklists/InspectionChecklistsPage.tsx
- frontend/src/pages/inspection-plans/InspectionPlansPage.tsx
- frontend/src/pages/inspection-prep/InspectionPrepPackagesPage.tsx

## Governance rule for all next waves
No wave closes without in-repo updates to:
- docs/CORPORATE_READINESS_COMPLETION_REPORT.md
- docs/CORPORATE_READINESS_REMAINING_GAPS.md
- docs/CORPORATE_READINESS_NEXT_STEPS.md
