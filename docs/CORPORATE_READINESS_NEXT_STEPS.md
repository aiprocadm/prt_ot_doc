# Corporate Readiness Next Steps

_Date:_ 2026-03-22

## Immediate next wave
1. Do a route-family consistency sweep for tenant enforcement, authz, structured errors, correlation-id propagation, and audit logging.
2. Build the first operational workspace projection APIs: attention center, task inbox, readiness blockers, recent drafts, recommendation blocks.
3. Consume the hardened `/api/pwa/bootstrap` contract from the frontend and implement offline queue state, retry/resume, and conflict UI.
4. Separate production orchestration from mock/stub providers in approval/sign/EDO and expose provider mode clearly in diagnostics.

## Second wave after that
1. Add persisted data-quality issues and blocker severity models for employees, companies/sites, templates/documents, training, PPE, and contractors.
2. Strengthen document lifecycle readiness, dependency map foundations, rerun progress semantics, and deterministic render snapshot metadata.
3. Turn admin into a true operational console for tenants, providers, queues/jobs, data quality, and readiness diagnostics.
4. Expand observability, cleanup jobs, watchdogs, and runbooks.

## Guardrails
- Keep document core stable; strengthen it without radical redesign.
- Preserve tenancy/authz invariants.
- Never present mock/stub integrations as production-ready.
- Document every remaining gap explicitly in-repo.
