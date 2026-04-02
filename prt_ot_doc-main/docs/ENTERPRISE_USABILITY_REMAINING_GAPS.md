# Enterprise Usability Remaining Gaps
**Version:** 1.0  
**Date:** March 24, 2026  
**Status:** Initial Assessment (Pre-Phase 2)

---

## Remaining Gaps by Category

These are the gaps identified in `ENTERPRISE_USABILITY_AUDIT.md`. They will be addressed in Phases 2–11. Update after each phase completes.

---

## Critical Gaps (Phase 2–5: Must Address for Corporate Use)

### Consistency Gaps (Phase 2)

| Gap | Files Affected | Impact | Status |
|-----|----------------|--------|--------|
| Tenant context not enforced uniformly | All route handlers | Medium | 🔲 Phase 2 |
| Permission checks vary across endpoints | route/* | High | 🔲 Phase 2 |
| Error responses inconsistent | All endpoints | Medium | 🔲 Phase 2 |
| Correlation ID missing from some paths | Background jobs | High | 🔲 Phase 2 |
| Audit logging incomplete | Sensitive operations | High | 🔲 Phase 2 |
| Frontend: route permission checks missing | All pages | High | 🔲 Phase 2 |
| Frontend: action permission checks missing | All components | High | 🔲 Phase 2 |
| Frontend: loading/error/empty states inconsistent | Data-fetching pages | Medium | 🔲 Phase 2 |
| Frontend: unsaved changes protection missing | Forms, wizards | High | 🔲 Phase 2 |

### Operational Visibility Gaps (Phase 3)

| Gap | Impact | Status |
|-----|--------|--------|
| No role-based workspaces | High | 🔲 Phase 3 |
| No task inbox | High | 🔲 Phase 3 |
| No attention center | High | 🔲 Phase 3 |
| No blocker surfacing | High | 🔲 Phase 3 |
| No recommendation engine | Medium | 🔲 Phase 3 |
| No landing page with urgent context | High | 🔲 Phase 3 |
| No "what's next" guidance | High | 🔲 Phase 3 |

### Document Lifecycle Gaps (Phase 4)

| Gap | Current Status | Impact | Status |
|-----|----------------|--------|--------|
| Lifecycle not unified (template → approve → sign → archive) | Partial | High | 🔲 Phase 4 |
| Readiness score calculation missing | Not implemented | High | 🔲 Phase 4 |
| Dependency map (NPA → template → document → route) | Not implemented | Medium | 🔲 Phase 4 |
| Render metadata not persisted | Ad-hoc | High | 🔲 Phase 4 |
| Idempotent rerun logic missing | Various implementations | High | 🔲 Phase 4 |
| Document passport not complete | Incomplete | Medium | 🔲 Phase 4 |

### Non-Production Fallback Gaps (Phase 5)

| Gap | Files | Status | Plan |
|-----|-------|--------|------|
| Approval/sign orchestration mixed with fallback | approval_signing_v1.py | 🔲 Phase 5 | Isolate or implement |
| EDO workflow has mock paths | edo_workflow.py | 🔲 Phase 5 | Isolate or implement |
| Integration stubs embedded | integrations/stubs.py | 🔲 Phase 5 | Separate + document |
| Pipeline handlers depend on fallback | pipeline_step_handlers.py | 🔲 Phase 5 | Real handlers + fallback path |
| Document jobs use deferred semantics | document_jobs_required.py | 🔲 Phase 5 | Reliable orchestration |
| Provider mode not explicit | Various | 🔲 Phase 5 | Feature flag + diagnostics |
| No non-production vs. production mode clarity | Codebase wide | 🔲 Phase 5 | Clear separation |

---

## High-Priority Gaps (Phase 6–9: Operational Hardening)

### Data Quality Gaps (Phase 6)

| Gap | Scope | Impact | Status |
|-----|-------|--------|--------|
| No incomplete entity detection | Employees, companies, documents, training, PPE, contractors | High | 🔲 Phase 6 |
| No missing relation detection | Cross-entity refs | Medium | 🔲 Phase 6 |
| No expiry tracking | Medical checkups, PPE, training, credentials | High | 🔲 Phase 6 |
| No data quality rule engine | All entities | High | 🔲 Phase 6 |
| No blocker calculation from data quality | Impact analysis | High | 🔲 Phase 6 |
| No data quality API for frontend | Dashboard/blockers | High | 🔲 Phase 6 |
| No admin data quality dashboard | Visibility | High | 🔲 Phase 6 |
| No bulk remediation actions | Batch fixing | Medium | 🔲 Phase 6 |

### PWA/Offline Gaps (Phase 7)

| Gap | Impact | Status |
|-----|--------|--------|
| Limited offline-usable dictionaries | Medium | 🔲 Phase 7 |
| Weak draft persistence | High | 🔲 Phase 7 |
| No offline queue UX | High | 🔲 Phase 7 |
| No conflict resolution UX | High | 🔲 Phase 7 |
| No offline indicator UI | Medium | 🔲 Phase 7 |
| No sync diagnostics for users | Medium | 🔲 Phase 7 |
| Limited field scenario support | High | 🔲 Phase 7 |
| No offline retry/resume guidance | High | 🔲 Phase 7 |

### Operational Page Gaps (Phase 8)

All 12 operational pages need enhancement (not rewrite):

| Page | Gaps | Status |
|------|------|--------|
| AdminPage | Next actions, blockers, bulk ops, diagnostics | 🔲 Phase 8 |
| ContractorsPage | Readiness, next actions, bulk approve | 🔲 Phase 8 |
| ReferencePage | Version history, template resolution, bulk upload | 🔲 Phase 8 |
| SettingsPage | Role breakdown, workflow customization, preferences | 🔲 Phase 8 |
| ActivitiesPage | Filtering, bulk actions, search | 🔲 Phase 8 |
| MedicalPage | Readiness, bulk reschedule, deep links | 🔲 Phase 8 |
| FireSafetyPage | Compliance status, blocker context, bulk remediation | 🔲 Phase 8 |
| FireTrainingPage | Completion status, bulk enroll, acknowledgement | 🔲 Phase 8 |
| FireInspectionsPage | Readiness, bulk schedule, integration links | 🔲 Phase 8 |
| InspectionChecklistsPage | Usage metrics, version mgmt, bulk deploy | 🔲 Phase 8 |
| InspectionPlansPage | Coverage map, timeline, bulk schedule | 🔲 Phase 8 |
| InspectionPrepPackagesPage | Readiness score, required docs, asset allocation | 🔲 Phase 8 |

### Admin/Governance Gaps (Phase 9)

| Capability | Impact | Status |
|------------|--------|--------|
| Tenant health dashboard | High | 🔲 Phase 9 |
| Outbox/webhook diagnostics | High | 🔲 Phase 9 |
| Integration readiness API | High | 🔲 Phase 9 |
| Provider mode diagnostics | High | 🔲 Phase 9 |
| Queue/job health indicators | High | 🔲 Phase 9 |
| Audit overview API | High | 🔲 Phase 9 |
| Data quality summary API | High | 🔲 Phase 9 |
| Billing/usage API | Medium | 🔲 Phase 9 |
| Startup readiness API | Medium | 🔲 Phase 9 |
| Feature enablement UI | Medium | 🔲 Phase 9 |

---

## Medium-Priority Gaps (Phase 10–11: Reliability & Tests)

### Reliability Gaps (Phase 10)

| Gap | Impact | Status |
|-----|--------|--------|
| Retry strategy inconsistent across jobs | Medium | 🔲 Phase 10 |
| No Dead-Letter Queue (DLQ) pattern | High | 🔲 Phase 10 |
| No heartbeat/watchdog | Medium | 🔲 Phase 10 |
| No failed job diagnostics API | High | 🔲 Phase 10 |
| No cleanup/integrity check Jobs | Medium | 🔲 Phase 10 |
| Incomplete health/readiness coverage | Medium | 🔲 Phase 10 |
| No comprehensive logging standards | Medium | 🔲 Phase 10 |
| No metrics collection | Medium | 🔲 Phase 10 |
| No alerting strategy | High | 🔲 Phase 10 |
| No runbooks / operational guides | High | 🔲 Phase 10 |

### Test Coverage Gaps (Phase 11)

| Area | Baseline | Target | Gap | Status |
|------|----------|--------|-----|--------|
| Tenant isolation tests | ? | > 90% | 🔲 | 🔲 Phase 11 |
| Permission check tests | ? | > 90% | 🔲 | 🔲 Phase 11 |
| Document lifecycle tests | ? | > 85% | 🔲 | 🔲 Phase 11 |
| Readiness/blocker tests | 0% | > 90% | 🔴 | 🔲 Phase 11 |
| Task/workspace tests | 0% | > 80% | 🔴 | 🔲 Phase 11 |
| Workflow/orchestration tests | ? | > 80% | 🔲 | 🔲 Phase 11 |
| Offline sync tests | ? | > 85% | 🔲 | 🔲 Phase 11 |
| Frontend page tests | ? | > 70% | 🔲 | 🔲 Phase 11 |

---

## Architecture Debt (Refactoring Opportunities)

### File Size Hotspots

| File | Size | Consolidation Opportunity | Work Required |
|------|------|--------------------------|----------------|
| models.py | ~123 KB | Split into domain modules | Major |
| tasks.py | ~76 KB | Split by domain/queue | Major |
| router.py | ~55 KB | Lighten dispatch coupling | Medium |
| risk.py | ~49 KB | Monitor for split | Medium |
| pipeline.py | ~43 KB | Modularize orchestration | Major |

### Duplicate Module Boundaries

| Issue | Impact | Status |
|-------|--------|--------|
| pipeline.py vs. pipelines_orchestrator.py | Unclear ownership | 🔲 Investigate |
| Multiple task orchestration patterns | Consistency | 🔲 Normalize |
| Snapshot generation scattered | Architecture | 🔲 Centralize |

---

## External Dependencies Not Yet Addressed

| Dependency | Purpose | Status |
|------------|---------|--------|
| 1С Integration (stub) | Enterprise ERP sync | 🔲 Real impl or explicit fallback |
| ЭДО Integration (mock) | E-signature/document exchange | 🔲 Real impl or explicit fallback |
| ФРДО Integration (stub) | Federal register | 🔲 Real impl or explicit fallback |
| ЕИСОТ Integration (stub) | Employee risk systems | 🔲 Real impl or explicit fallback |
| WebSocket (polling fallback) | Real-time updates | ⚠️ Acceptable for now |
| Outbox/webhook delivery | Event propagation | ✅ Implemented |

---

## Known Workarounds

(To be populated as gaps are encountered)

---

## Blocked Items

(To be tracked if unexpected dependencies found)

---

## Success Criteria for Gap Closure

By end of Phase 11, ALL gaps should be:
- ✅ Addressed (code changes OR documented workaround), OR
- ✅ Explicitly deferred (with reason + next-wave plan)

**No gaps should remain unaddressed or undocumented.**

---

## Gap Resolution Strategy

### By Phase
| Phase | Gaps Resolved | Validation |
|-------|---------------|-----------|
| 2 | Consistency (9 backend + 5 frontend) | Consistency test suite passes |
| 3 | Visibility (7 gaps) | User can see tasks/blockers on login |
| 4 | Document lifecycle (6 gaps) | Document flows end-to-end |
| 5 | Fallback elimination (7 gaps) | All non-production paths isolated/documented |
| 6 | Data quality (8 gaps) | Admin sees complete data quality overview |
| 7 | Offline/PWA (8 gaps) | User can work offline and sync |
| 8 | UX maturity (12 pages × ~5 gaps each) | Users complete daily workflows on pages |
| 9 | Admin/governance (10 gaps) | Admin can diagnose any operational issue |
| 10 | Reliability (10 gaps) | Runbooks functional, failures handled gracefully |
| 11 | Tests (8 areas) | Coverage targets met |

---

**Last Updated:** March 24, 2026  
**Status:** Initial inventory from Audit phase
