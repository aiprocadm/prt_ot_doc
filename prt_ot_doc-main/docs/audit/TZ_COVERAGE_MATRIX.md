# TZ_COVERAGE_MATRIX

Status: `Done` / `Partial` / `Gap`. Priority: `P0` / `P1` / `P2`.

| TZ area | Wave | Priority | Status | Canonical implementation / gap anchor |
|---|---|---|---|---|
| Baseline traceability (`TZ -> code -> tests`) | 0 | P0 | Partial | `docs/audit/TZ_COVERAGE_MATRIX.md`, `ACCEPTANCE_TEST_MATRIX.md`; needs per-item owner and target wave discipline |
| Tenant context required for business routes | 1 | P0 | Done | `backend/app/middleware/tenant.py`, tests in `tests/test_tenant_header_required.py` |
| Tenant isolation and scoped DB usage | 1 | P0 | Partial | `backend/app/db/session.py`, `backend/app/api/dependencies.py`; requires full endpoint sweep sign-off |
| IAM (RBAC/ABAC) consistency across all modules | 1 | P0 | Partial | `backend/app/core/security.py`, `docs/authz.md`; route-level exceptions still need normalization |
| Structured error contract (`code/type/message/details/field_errors/correlation_id/timestamp`) | 1 | P0 | Done | `backend/app/api/error_handlers.py` |
| Audit + correlation coverage for critical operations | 1 | P0 | Partial | `backend/app/services/audit.py`, `backend/app/tasks.py`; requires complete cross-module checklist |
| Reliability layer (idempotency/retries/DLQ/poison) | 1 | P0 | Partial | `backend/app/services/idempotency.py`, `backend/app/tasks.py`, `backend/app/api/routes/jobs.py` |
| Self-healing / stuck jobs watchdog | 1 | P1 | Partial | `backend/app/tasks.py` + Celery beat; expanded watchdog policies required |
| Document core pipeline unified end-to-end | 2 | P0 | Partial | `backend/app/modules/pipelines/*`, `backend/app/api/v1/router.py`; not all flows auto-chain generate->headers->pdf |
| Document Readiness Score centralized and explainable | 2 | P0 | Partial | `backend/app/modules/projections/services.py`, `backend/app/api/routes/workspace.py`; full document-level canonical score pending |
| Diff/compare/dependency map completeness | 2 | P1 | Gap | requires dedicated version-diff and dependency graph closures |
| Risks/PPE/Training/Incidents/Inspections full contour | 3 | P1 | Partial | domain modules exist in `backend/app/domains/*`; not all lifecycle links finalized |
| Universal timeline + attention center coverage | 3 | P1 | Partial | `frontend/src/components/common/AttentionPanel.tsx`, workspace APIs; universal event timeline still incomplete |
| Frontend role workspaces + command workflows | 4 | P1 | Partial | dashboards/workspaces exist; command bar and full scenario UX require completion |
| Mobile/offline conflict resolver maturity | 4 | P1 | Partial | `backend/app/api/routes/pwa_sync.py`, `frontend/src/components/common/ConnectivityBanner.tsx` |
| Integrations/EDO/signature production adapters | 5 | P0 | Gap | stubs in `backend/app/services/integrations/stubs.py`; production adapters pending |
| Acceptance quality gates (tests/perf/security) | cross-wave | P0 | Partial | quality gates configured, but full TZ traceability and SLO verification matrix still expanding |
