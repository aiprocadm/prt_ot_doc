# Operational Maturity Plan (No Rewrite)

## Objectives

Deliver enterprise-usable operational maturity without breaking existing working flows.

Core constraints:
- no massive rewrite
- preserve working document core and existing snapshot/projection APIs
- tenant-aware, permission-aware, audit-aware changes only
- each increment tested and documented

## Priority order

Priority 1:
1. consistency hardening across backend/frontend
2. role workspaces + attention/tasks/blockers
3. document lifecycle centralization hardening

Priority 2:
1. remove corporate-blocking stub/mock/deferred points where avoidable
2. data quality + blockers/readiness integration
3. admin/governance/diagnostics completion

Priority 3:
1. practical PWA/field mode hardening
2. operational UX cleanup
3. reliability/runbooks/tests expansion

## Phase plan

### Phase 1: Operational maturity audit and baseline docs
- produce factual audit and explicit gap map
- freeze verified metrics and confirmed blocker surfaces
- define target acceptance criteria by phase

Deliverables:
- docs/OPERATIONAL_MATURITY_AUDIT.md
- docs/OPERATIONAL_MATURITY_PLAN.md

### Phase 2: Consistency hardening pass
Backend:
- normalize tenant context checks for business endpoints
- normalize permission checks for read/write/bulk/export/search
- normalize structured errors and correlation-id propagation
- ensure audit on sensitive actions and tenant/correlation in jobs

Frontend:
- route-level and action-level permission behavior consistency
- unified loading/error/empty states for operational pages
- unsaved-change handling in critical forms/wizards

Acceptance:
- no critical path route without tenant/authz contract
- consistent error envelope on prioritized modules

### Phase 3: Role workspaces, attention, task inbox, readiness
Backend:
- complete unified projection surfaces for attention/task/blocker/next-action timeline
- expose blockers and recommendations cross-domain

Frontend:
- post-login role cockpit with overdue, blocked, attention-required and next actions
- deep links from attention items to operational screens

Acceptance:
- user can identify top priorities in under 10 seconds after login

### Phase 4: Document core central lifecycle hardening
- unify lifecycle contract: template -> readiness -> branding -> replace -> pdf -> approval -> sign -> edo -> archive
- strengthen scope-based template resolution (system/tenant/company/site)
- finalize readiness score reasons/actions
- persist deterministic render metadata and rerun semantics

Acceptance:
- lifecycle state is explainable and observable end-to-end
- no regressions on upload/version/lint/preview/branding/replace/pdf/packs

### Phase 5: Remove/contain corporate-blocking stubs
- isolate non-production adapters explicitly
- display provider mode in admin diagnostics and docs
- replace avoidable deferred stubs with internal orchestration

Acceptance:
- non-production modes are explicit and non-misleading
- internal orchestration has audit/retry/status/diagnostics

### Phase 6: Data quality as operational loop
- detect and persist blockers: incomplete entities, missing relations, expired critical records, feasible duplicates
- integrate blockers with workspaces/readiness dashboards/attention center

Coverage minimum:
- employees, companies/sites, templates/documents, training, PPE, contractors

### Phase 7: PWA/field readiness hardening
- extend bootstrap dictionaries and permissions for offline use
- improve local drafts and offline queue UX
- conflict resolution UX, retry/resume UX, sync diagnostics
- support selected field scenarios (briefing mark, incident draft, checklist draft, task/comment, media sync, training acknowledgment)

### Phase 8: UX hardening for daily corporate use
- unify registry/entity card patterns
- contextual empty states and guidance
- obvious primary CTA and reduced clutter

Focus screens:
- admin, contractors, reference, settings, medical, fire safety/training/inspections, inspection prep, dashboards, client portal ops pages

### Phase 9: Admin/governance/diagnostics
- tenant health
- outbox/webhook diagnostics
- provider mode diagnostics
- queue/job diagnostics
- audit/data-quality/billing/usage overviews
- startup readiness and module enablement visibility

### Phase 10: Reliability, observability, runbooks
- retry and poison handling consistency
- heartbeat/watchdog and failed job diagnostics
- cleanup and integrity checks
- improved readiness health checks
- reproducible local bootstrap and CI verification path
- runbook updates

### Phase 11: Tests after each major block
- backend unit + integration
- frontend tests
- contract tests where needed

Coverage priority:
- tenant isolation
- authz
- document lifecycle/readiness
- blockers/data quality
- tasks/attention/workspaces
- approval/sign/edo orchestration
- offline sync edge cases

## Execution model

- small vertical increments (backend projection + frontend consumption + tests + docs)
- each increment avoids changing public behavior unless explicitly hardened
- no architecture-only rewrites without operational gain
