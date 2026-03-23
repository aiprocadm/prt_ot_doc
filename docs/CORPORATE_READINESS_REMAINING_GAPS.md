# Corporate Readiness Remaining Gaps

Date: 2026-03-23

## Tier 1 enterprise rollout blockers
### 1) Consistency normalization is incomplete
- Full endpoint-by-endpoint sweep for tenant/authz/errors/audit/correlation is not completed across all route families.
- Permission behavior is still heterogeneous on read/write/bulk/export/search edges.

### 2) Operational workspace is incomplete
- No fully unified role-based workspace across modules.
- Attention center and task inbox behavior are not yet universally integrated.
- Readiness blocker explanations and recommendations are not yet consistently visible across scenarios.

### 3) Stub/mock/deferred seams still block corporate rollout
- backend/app/api/routes/ws_stub.py is deferred.
- backend/app/celery/tasks/document_jobs_required.py contains deferred compatibility behavior.
- backend/app/services/pipeline_step_handlers.py includes deferred stages.
- backend/app/services/integrations/stubs.py contains non-production adapters.
- backend/app/api/routes/approval_signing_v1.py, backend/app/api/routes/approval_orchestration.py, backend/app/api/routes/edo_workflow.py retain stub/mock semantics.

### 4) Data quality layer not yet first-class and persisted platform-wide
- No complete persisted issue model across employees, companies/sites, templates/documents, training, PPE, contractors.
- Cross-scenario blocker impact is still partial.

### 5) Mobile/offline remains partial
- PWA shell exists, but queue/conflict/retry-resume/drafts UX is not enterprise-complete.
- Selected field scenarios need completion and hardening.

### 6) Admin diagnostics not yet operationally complete
- Governance console still lacks full tenant readiness + provider mode + queue/job + data quality + usage/billing + environment consolidation.

## Tier 2 blockers
### 1) Reliability hardening
- Retry policies, DLQ/poison handling, watchdog/heartbeat, failed-job diagnostics, cleanup/integrity checks need normalization.

### 2) Document core centralization in one lifecycle plane
- Lifecycle readiness visibility and deterministic traceability still need deeper unification.

### 3) UX consistency and declutter
- Thin/partial pages remain in priority modules and need operational conversion.

## High-risk structural debt
- backend/app/models/models.py
- backend/app/tasks.py
- backend/app/api/v1/router.py
- backend/app/api/routes/risk.py
- backend/app/services/pipeline.py
- backend/app/api/routes/packs.py
- backend/app/api/routes/documents.py
- backend/app/services/pipelines_orchestrator.py

## Parallel module-structure debt
- backend/app/modules/approval
- backend/app/modules/approvals

## Residual risk statement
Without closure of Tier 1 blockers, enterprise rollout will remain high risk even with strong feature breadth.
