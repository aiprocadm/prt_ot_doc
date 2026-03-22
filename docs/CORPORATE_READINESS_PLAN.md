# Corporate Readiness Plan

_Date:_ 2026-03-22

## Guiding rules
1. Do not delete working features for architecture purity.
2. Avoid massive rewrite.
3. Improve tenant-safe, permission-safe, audited seams incrementally.
4. Keep non-production providers explicit.
5. Record every decision in repository docs.

## Recommended implementation order
1. Consistency hardening.
2. Operational workspace layer.
3. Document core centralization.
4. Removal/isolation of corporate-blocking stubs.
5. Data quality + readiness blockers.
6. Mobile/PWA practical hardening.
7. Admin/governance/diagnostics.
8. Reliability/observability/runbooks.
9. Final UX cleanup and tests.

## This wave plan vs execution
### Planned for this wave
- Refresh the audit into a corporate-readiness framing.
- Strengthen one high-value enterprise seam without rewrite.
- Produce explicit completion and remaining-gap documentation.

### Executed in this wave
- Completed a factual corporate-readiness audit based on runtime code.
- Hardened `/api/pwa/bootstrap` from a simplified payload to an authenticated projection API suitable for the next offline/mobile wave.
- Added corporate-readiness artifacts documenting confirmed production-ready foundations, partial areas, stub/mock/deferred seams, and rollout blockers.

## Near-term backlog
### Phase B — consistency hardening
- Audit business routes for tenant enforcement, authz normalization, error envelope consistency, correlation-id propagation, and audit logging.
- Verify background jobs preserve tenant context and expose uniform diagnostics.

### Phase C — operational workspace layer
- Introduce role-based workspace projections.
- Build attention center, task inbox, readiness blockers, recent drafts, recommendation blocks, and deep-link contracts.

### Phase D — document core strengthening
- Keep the existing core, but make readiness, dependency map, snapshot reproducibility, rerun progress, and passport completeness first-class.

### Phase E — stub removal / isolation
- Keep provider contracts stable while cleanly isolating non-production adapters in admin/readiness diagnostics and API metadata.

### Phase F — mobile/PWA hardening
- Add frontend offline queue model, sync state UI, retry/resume flow, conflict resolution UX, and robust drafts persistence on top of the improved bootstrap payload.

## Success criteria for the next wave
- A user can log in and immediately see what is overdue, blocked, or assigned.
- Non-production provider modes are impossible to mistake for production integrations.
- Offline/mobile flows expose real sync state and conflict semantics.
- Corporate rollout blockers are measurable in diagnostics and docs rather than hidden in code paths.
