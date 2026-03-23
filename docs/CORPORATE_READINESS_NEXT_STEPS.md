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
- normalized audit context forwarding (`request_id`, `user_agent`) for write operations in safety-ops, tasks, inspections, attestations, companies routes;
- added test coverage for audit-context forwarding helper behavior.
- extended the same consistency rule to additional write-heavy modules: files, packs, prescriptions;
- validated with focused backend tests.
- applied structured error envelope normalization in prescriptions helper not-found flows and pack archive download validation flows.
- applied permission parity hardening in pack routes via explicit read/write access dependencies and role split.
- applied incidents-route consistency hardening: structured 400 error envelopes for validation failures and audit trace/user-agent propagation for incident create logging.
- applied training-route consistency hardening: explicit read/write access dependencies for mutation endpoints and structured 400 error envelopes for validation failures.
- applied ppe-route consistency hardening: explicit read/write access dependencies for mutation endpoints and structured 400 error envelopes for issue validation failures.
- applied orders-route consistency hardening: explicit read/write access dependencies for mutation endpoints and structured 422 error envelopes for order-status validation failures.
- applied persons-route consistency hardening: explicit read/write access dependencies and structured 400/422 error envelopes for validation/domain failures.
- applied invoices-route consistency hardening: explicit read/write access dependencies and structured 400/422 error envelopes for validation/domain failures.
- applied contracts-route consistency hardening: explicit read/write access dependencies and structured 400/422 error envelopes for validation/domain failures.
- applied inspections-route consistency hardening: explicit read/write access dependencies and structured 400 error envelopes for domain validation failures.
- applied tasks-route consistency hardening: parity test coverage for read/write role split and structured 422 error envelopes for validation failures.
- applied companies-route consistency hardening: explicit read/write access dependencies and structured 422 error envelopes for validation failures.
- applied sites-route consistency hardening: explicit read/write access dependencies with parity regression coverage.
- applied attestations-route consistency hardening: explicit read/write access dependencies with parity regression coverage.
- applied departments-route consistency hardening: explicit read/write access dependencies with parity regression coverage.
- applied safety-ops consistency hardening: added read/write access parity regression coverage for existing role split.
- applied briefings-route consistency hardening: explicit permission constants and structured 400 error envelopes for completion validation failures.
- applied files consistency hardening: added read/write access parity regression coverage for existing upload/read role split.
- applied prescriptions-route consistency hardening: explicit read/write access dependencies with parity regression coverage.
- applied incidents-route consistency hardening: explicit read/write access dependencies with parity regression coverage alongside structured 400 error contract coverage.
- applied audit-route consistency hardening: structured 400 error envelopes for backward-list validation failures.
- applied risk-route consistency hardening: structured 422 error envelopes for risk-level filter validation failures.
- applied admin-users-route consistency hardening: structured 422 error envelopes for role-assignment validation failures.
- applied replace-route consistency hardening: structured 400/422 error envelopes for input validation failures and fixed unreachable empty-`from` map validation.
- applied edo-workflow-route consistency hardening: structured 422 error envelopes for approval-route rules validation and aligned create/update validation behavior.
- applied approval-orchestration-route consistency hardening: structured 422 error envelopes for webhook request validation failures.
- applied documents-route consistency hardening: structured 400 error envelopes for document-generation and batch-input validation failures.
- applied approval-signing-v1-route consistency hardening: structured 422 error envelopes for sign and EDO validation failures.
- applied packs-route consistency hardening: structured 400 error envelopes for remaining pack validation failures.
- applied risk-route additional consistency hardening: structured 400 error envelope for fallback assessment-input validation.
- applied billing-route consistency hardening: shared structured 400 error helper for plan-change validation.
- applied medical-route consistency hardening: explicit read/write role constants with parity regression coverage.
- applied approval-orchestration-route parity hardening: explicit read/write role constants with parity regression coverage.

Immediate next substep:
- continue endpoint-by-endpoint permission parity sweep on read/write/bulk/export/search edges for remaining route families and add focused regression tests per family.

Exit criteria:
- no route family exits wave without consistency checklist pass,
- test evidence for tenant/authz/error contract is added.

## Wave 2: Operational workspace layer
1. Expand role-based attention center and task inbox projections.
2. Add readiness blockers with severity, reasons, and recommended actions.
3. Add recent drafts/recent items and recommendation blocks.
4. Add deep links from dashboards to action screens.

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
1. Harden /api/pwa/bootstrap projections for field workflows.
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
