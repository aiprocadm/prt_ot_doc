# Corporate Readiness Next Steps

_Date:_ 2026-03-23

## Immediate implementation wave
1. Finish the route-family consistency sweep covering tenant enforcement, authz normalization, structured errors, correlation-id propagation, and audit logging (after the latest audit-coverage expansion in public API/client portal/medical/NPA/audit routes).
2. Build the first real operational workspace projection APIs: attention center, task inbox, readiness blockers, recent drafts/items, and recommendations.
3. Start frontend consumption of the hardened `/api/pwa/bootstrap` contract — now including offline capability flags, failed-conflict projections, draft policy, and conflict-resolution hints — and add offline queue state, sync state UX, retry/resume UX, and conflict handling.
4. Separate internal production orchestration from mock/stub providers in approval/sign/EDO and make provider mode explicit in diagnostics and API metadata.

## Latest completed delta
1. Added a new consistency hardening pass for sensitive write actions in:
	- `backend/app/api/routes/public_api.py`
	- `backend/app/api/routes/client_portal.py`
	- `backend/app/api/routes/medical.py`
	- `backend/app/api/routes/npa.py`
	- `backend/app/api/routes/audit.py`
2. Revalidated backend regression suite (`114 passed`) after the hardening pass.

## Second implementation wave
1. Add persisted data-quality issues and blocker severity models for employees, companies/sites, templates/documents, training, PPE, and contractors.
2. Strengthen document lifecycle readiness, scope resolution, dependency mapping, rerun semantics, deterministic snapshots, and document passport completeness.
3. Turn admin into a real operational governance console for tenant readiness, provider modes, jobs, data quality, usage/billing, and environment diagnostics.
4. Normalize retries, poison handling, watchdogs, cleanup tasks, integrity checks, and update the main operational runbooks.

## Acceptance focus
- Tenant isolation.
- Authz consistency.
- Document lifecycle and readiness.
- Task/attention/readiness projections.
- Approval/sign/EDO orchestration.
- Offline sync edge cases.
- Converted operational pages.

## Guardrails for all next waves
- Keep the existing document core stable and strengthen it incrementally.
- Preserve tenancy/authz invariants.
- Do not mask stub/mock limitations behind polished UX.
- Prefer scenario-first and role-based UX over adding more disconnected pages.
- Record every decision and remaining gap in-repo.
