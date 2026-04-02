# Operational Maturity Remaining Gaps

## A. Corporate-blocking integration/orchestration gaps

1. Deferred websocket channel
- backend/app/api/routes/ws_stub.py now provides polling fallback (no longer 501 deferred), but true websocket transport/channel still remains pending.

2. Compatibility/deferred job bridge semantics
- backend/app/celery/tasks/document_jobs_required.py updated to internal fallback for known absent bridges (export_report/sync_integration), but wider async consistency and diagnostics alignment across all job surfaces is still required.

3. Non-production provider defaults in critical approval/sign/edo surfaces
- backend/app/api/routes/approval_signing_v1.py defaults moved to internal-fallback (legacy stub compatibility remains)
- backend/app/api/routes/approval_orchestration.py defaults moved to internal-fallback
- backend/app/api/routes/edo_workflow.py defaults moved to internal-fallback (legacy compatibility shim remains)
- backend/app/services/integrations/stubs.py (stub adapters)

Note:
- stub adapter diagnostics were hardened (explicit non-production telemetry), but certified production adapters are still required to fully close this blocker class.

4. Deferred stage outcome on disabled integration paths
- backend/app/services/pipeline_step_handlers.py updated for EDO stage to internal fallback completion (no deferred), but equivalent consistency should still be verified across all disabled-adapter stage paths.

## B. Consistency hardening gaps

1. Permission normalization
- route-level and action-level permission patterns are not fully uniform across all domain routes.

2. Error envelope normalization
- structured errors were normalized for critical approval_signing_v1 paths and key edo_workflow not-found/unauthorized paths, but envelope shape and detail fields are not yet completely consistent platform-wide (mixed legacy paths still remain).

3. Correlation-id propagation
- improved for approval_signing_v1, approval_orchestration and edo_workflow write/webhook paths; still needs full normalization across remaining critical read/write/async surfaces.

4. Audit consistency
- sensitive action audit exists but exposure and completeness vary between modules.

## C. Operational UX and role workspace gaps

1. Unified post-login role cockpit still incomplete
- attention/tasks/blockers are available but not consistently integrated into all role home flows.

2. Operational maturity of projection pages
- several pages provide real data but still need better next-actions, deep links, bulk actions, and scenario guidance.

3. Empty-state and blocker explainability consistency
- not unified across all operational registries.

## D. Data quality and readiness loop gaps

1. Data quality issues are not yet uniformly persisted and surfaced as daily blockers for all priority entities.
2. Readiness reasons/actions need stronger, cross-module explainability and prioritization.

## E. PWA/field mode gaps

PWA baseline exists and bootstrap returns strong payload, but field enterprise maturity still requires:
- broader offline dictionaries/contracts by scenario
- stronger local drafts lifecycle
- clearer retry/resume/conflict UX
- stronger user-facing sync diagnostics for recovery

## F. Reliability and operations gaps

1. Retry and poison handling consistency needs normalization across async flows.
2. Runbook/diagnostics coverage should be tightened for failed jobs and integrity checks.
3. CI verification path for major hardening phases should be codified per operational domain.
