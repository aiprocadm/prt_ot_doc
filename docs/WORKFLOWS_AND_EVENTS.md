# WORKFLOWS_AND_EVENTS

## Purpose
This document is the canonical cross-module map for long-running workflows, approval/signature transitions, async jobs, and event-emission touchpoints. It exists so the next implementation wave can understand execution flow from the repository itself instead of relying on prompt memory.

## Canonical orchestration paths
- **Workflow APIs:** `backend/app/modules/workflow/`
- **Approval/signature APIs:** `backend/app/modules/approvals/`, `backend/app/modules/sign/`, `backend/app/modules/edo/`
- **Document pipeline orchestration:** `backend/app/services/pipeline.py`, `backend/app/modules/pipelines/`, `backend/app/tasks.py`
- **Notification/search integration points:** `backend/app/modules/search/`, `backend/app/services/outbox.py`, `backend/app/services/webhooks.py`
- **Frontend workflow/task surfaces:** `frontend/src/pages/workflow/`, `frontend/src/pages/approvals/`, `frontend/src/pages/signatures/`, `frontend/src/pages/notifications/`

## Primary workflow families

### 1. Document generation and branded output
1. Document/template selection starts in `frontend/src/pages/documents/DocumentsWizardPage.tsx`.
2. Request enters backend document APIs in `backend/app/api/routes/documents.py`.
3. Pipeline orchestration runs through `backend/app/services/pipeline.py` and async jobs in `backend/app/tasks.py`.
4. Header/footer application and layout presets resolve through `backend/app/modules/headers/` and `backend/app/modules/branding/`.
5. Result metadata is persisted to pipeline runs, including branding reproducibility hashes and preview/apply-headers payloads.

### 2. Approvals, signatures, and EDO
1. Approval routes are exposed from `backend/app/modules/approvals/`.
2. Signature state and journal logic live in `backend/app/modules/sign/` and `backend/app/modules/edo/`.
3. UI status/timeline surfaces render in `frontend/src/pages/approvals/` and `frontend/src/pages/signatures/`.
4. Critical state transitions should emit audit entries and outbox/webhook side effects instead of relying on UI-only state.

### 3. Training, risks, incidents, inspections, and prescriptions
- Domain flows are centered in `backend/app/modules/training/`, `backend/app/modules/risk/`, `backend/app/modules/incidents/`, and `backend/app/modules/inspections/`.
- Supporting enterprise registries/cards live in the mirrored frontend route areas under `frontend/src/pages/training/`, `frontend/src/pages/risk/`, `frontend/src/pages/incidents/`, `frontend/src/pages/inspections/`, and `frontend/src/pages/prescriptions/`.
- Cross-domain corrective-action and deadline tracking should route through workflow/tasks rather than module-local duplicate task systems where possible.

## Event and job principles
- **Audit first:** critical writes must remain auditable and tenant-scoped.
- **Outbox for external side effects:** webhook/integration dispatch should originate from persisted events, not inline best-effort callbacks.
- **Idempotency for critical writes:** document generation and similar mutation-heavy operations must preserve idempotent behavior.
- **Async transparency:** long-running jobs should expose status endpoints/UI states, not hidden background transitions.

## Known legacy/compatibility notes
- `backend/app/modules/approval/` remains in the repository for compatibility, but new work should target `backend/app/modules/approvals/`.
- Some generation flows still require an explicit `apply_headers` step rather than a fully chained `generate -> apply_headers -> pdf` pipeline. This is tracked in `KNOWN_LIMITATIONS.md` and `GAP_REPORT.md`.
