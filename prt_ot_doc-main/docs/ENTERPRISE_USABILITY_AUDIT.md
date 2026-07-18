# Enterprise Usability Audit — Archive (19)
**Audit Date:** March 24, 2026  
**Status:** Current state factual assessment  
**Scope:** Full platform codebase review with verified findings

---

## Executive Summary

The platform has progressed from "foundation with stubs" to a **strong enterprise-ready skeleton**, but remains incomplete for daily corporate use. The architecture is modular and substantial, but operational maturity, consistency hardening, and elimination of non-production fallback paths are now the primary blockers—not missing code.

**Core Finding:** The next phase must be **hardening and unification**, not expansion.

---

## Confirmed Archive Scale

| Metric | Count | Status |
|--------|-------|--------|
| Backend route files | 56 | Well-distributed across modules |
| Frontend page files | 75 | Mixed projection/full-feature coverage |
| Test files/artifacts | 302 | Substantial test contour |
| Module structure | Large modular monolith | Real modules, not mock scaffolding |

---

## Heaviest Files (Maintainability Risk)

| File | Size | Issue |
|------|------|-------|
| `backend/app/models/models.py` | ~123 KB | Core domain very large; needs refactoring |
| `backend/app/tasks.py` | ~76 KB | Celery tasks; architectural consolidation needed |
| `backend/app/api/v1/router.py` | ~55 KB | Entrypoint coupling; dispatch should be lighter |
| `backend/app/api/routes/risk.py` | ~49 KB | Domain-specific but heavy; consider split |
| `backend/app/services/pipeline.py` | ~43 KB | Pipeline orchestration bloated; needs modularization |
| `backend/app/api/routes/packs.py` | ~39 KB | Document packs; concerns mixed |
| `backend/app/api/routes/approval_signing_v1.py` | ~34 KB | Approval orchestration still hybrid |
| `backend/app/api/routes/documents.py` | ~33 KB | Document API surface; logic leakage |
| `backend/app/services/pipelines_orchestrator.py` | ~31 KB | Orchestration; duplicate concerns with pipeline.py |

**Architecture Debt:** These files represent maintainability points where consolidation, concern separation, or modular refactoring would reduce cognitive load.

---

## What Has Improved (Verified Facts)

### 1. WebSocket Stub → Polling Fallback

**File:** `backend/app/api/routes/ws_stub.py`

**Finding:** No longer returns bare 501. Now provides production-safe **polling fallback over outbox projections**.

**Status:** ✅ Better than deferred stub, but still not true WebSocket transport.

**Next Step:** Real WebSocket impl or keep fallback as explicit non-production mode.

---

### 2. PWA Fully Integrated

**File:** `frontend/vite.config.ts`

**Verified Features:**
- ✅ `vite-plugin-pwa` integrated
- ✅ Manifest defined
- ✅ Runtime caching configured
- ✅ `NetworkFirst` strategy for `/api/*` routes

**Status:** PWA is production integrated, not a future task. Do not rebuild from scratch.

---

### 3. Offline Bootstrap Strengthened

**Endpoint:** `/api/pwa/bootstrap`

**Current Payload:**
- ✅ `current_user`
- ✅ `route_permissions`
- ✅ `dictionaries`
- ✅ `offline_queue`
- ✅ `sync_state`
- ✅ `diagnostics`

**Assessment:** Good foundation for field/offline scenarios. Needs expansion per Phase 7.

---

### 4. Pages Migrated to Real Snapshot APIs

**Verified Pages Using Backend Snapshots** (not static or mock data):
- ✅ AdminPage
- ✅ ContractorsPage
- ✅ ReferencePage
- ✅ SettingsPage
- ✅ ActivitiesPage
- ✅ MedicalPage
- ✅ FireSafetyPage
- ✅ FireTrainingPage
- ✅ FireInspectionsPage
- ✅ InspectionChecklistsPage
- ✅ InspectionPlansPage
- ✅ InspectionPrepPackagesPage

**Status:** Frontend is **not a demo shell**. Mostly projection-based screens with real data binding, but operational maturity (next actions, blockers, bulk UX, empty states) still incomplete.

---

## Critical Non-Production Points (Confirmed)

These are the **enterprise-blocking barriers** that prevent corporate deployment:

### Backend

#### 1. `backend/app/celery/tasks/document_jobs_required.py`
- **Status:** Still uses compatibility/deferred/internal-fallback bridge semantics
- **Block:** Document job reporting is unreliable for real workflows
- **Impact:** High — job status/retry/diagnostics uncertain

#### 2. `backend/app/services/pipeline_step_handlers.py`
- **Status:** Integration stages and pipeline steps still dependent on fallback/provider mode
- **Block:** Workflow orchestration incomplete without real service definitions
- **Impact:** High — approval/sign/edo chains uncertain

#### 3. `backend/app/services/integrations/stubs.py`
- **Status:** Still contains full stub implementations for:
  - 1С integration
  - ЭДО (E-signature/Document exchange)
  - ФРДО (Federal register)
  - ЕИСОТ (Employee risk systems)
- **Block:** External integrations cannot be verified
- **Impact:** High — cannot deploy corporate-wide without real service enablement

#### 4. `backend/app/api/routes/approval_signing_v1.py`
- **Status:** Contains stub/internal-fallback provider paths
- **Block:** Approval orchestration logic mixed with fallback behavior
- **Impact:** Critical — approval/sign workflow unreliable

#### 5. `backend/app/api/routes/approval_orchestration.py`
- **Status:** Still has mock provider path
- **Block:** Orchestration logic unclear in production mode
- **Impact:** Critical — orchestration behavior not deterministic

#### 6. `backend/app/api/routes/edo_workflow.py`
- **Status:** Mock/stub semantics still embedded
- **Block:** E-document workflow not real
- **Impact:** Critical — document exchange/signature cannot be trusted

---

## Operational Maturity Gaps (Verified)

### Frontend Screens: Good Data Binding, Incomplete UX

The pages listed above already pull real data, but most are essentially:
- Registry + blockers card + link collection

**Missing for daily corporate use:**
- ❌ Rich scenario narratives (what workflows does this enable?)
- ❌ Explicit next actions (what should the user do now?)
- ❌ Bulk operations (cannot process > 1 item efficiently)
- ❌ Explainable readiness/blocker flows (why is this blocked? what to fix?)
- ❌ Role-specific context (what matters for my role?)
- ❌ Task inbox (where do my responsibilities surface?)

**Status:** Projection screens exist; daily-use maturity does not.

---

### Document Core: Strong, But Not Yet Unified Engine

**What Exists:**
- ✅ Template management
- ✅ Version history
- ✅ Linting
- ✅ Preview
- ✅ Branding/header-footer
- ✅ Replace
- ✅ PDF rendering
- ✅ Pack management

**What's Missing:**
- ❌ Unified lifecycle: template → readiness → replace → pdf → approval → sign → edo → archive
- ❌ Deterministic readiness score (why ready? why not?)
- ❌ Explicit dependency map (which NPA → which templates → which routes?)
- ❌ Persistent render metadata + snapshots
- ❌ Idempotent reruns + reliable async progress
- ❌ Explainable reasons + recommended actions

**Status:** Components work; orchestration incomplete.

---

### Admin Console: Better Than Before, Still Not Enterprise-Grade

**What's Improved:**
- ✅ Snapshots integrated
- ✅ Some operational sections exist

**What's Missing:**
- ❌ Provider mode diagnostics (is fallback active?)
- ❌ Tenant health dashboard
- ❌ Queue/job health indicators
- ❌ Integration readiness assessment
- ❌ Startup readiness diagnostics
- ❌ Governance/audit visibility
- ❌ Feature enablement overview

**Status:** Better than empty; not yet operationally useful.

---

## Tenant/Authz/Audit Consistency

### Confirmed Gaps

**Backend:**
- ❌ Not all business endpoints enforce tenant context uniformly
- ❌ Permission checks vary across read/write/bulk/export/search
- ❌ Error messages not consistently structured
- ❌ Correlation ID propagation incomplete
- ❌ Audit coverage inconsistent for sensitive actions
- ❌ Background jobs sometimes lose tenant context

**Frontend:**
- ❌ Route-level permission awareness incomplete
- ❌ Action-level permission awareness incomplete
- ❌ Forbidden actions sometimes visible (should be hidden/disabled)
- ❌ Loading/error/empty states inconsistent
- ❌ Unsaved-changes protection missing in critical forms

**Status:** Inconsistency across modules; refactoring required before scaling.

---

## Role-Based Workspaces / Attention / Tasks

### Current State

**Missing:**
- ❌ Role-based dashboards
- ❌ Task inbox
- ❌ Attention center
- ❌ Recent drafts
- ❌ Recent items
- ❌ Blocker surfacing
- ❌ Recommendations
- ❌ Deep links to next actions

**Impact:** Users log in and cannot immediately understand what's urgent/blocked/due.

**Status:** Not implemented; critical for daily corporate use.

---

## Data Quality + Readiness Blockers

### Current Gaps

**Missing Coverage:**
- ❌ No detection of incomplete entities
- ❌ No detection of missing critical relations
- ❌ No detection of expired critical records
- ❌ No persistent issue tracking
- ❌ No blocker exposure in dashboards/workspaces

**Minimum Coverage Needed:**
- Employees
- Companies/sites
- Templates/documents
- Training
- PPE
- Contractors

**Status:** Not implemented; blocking corporate readiness assessment.

---

## PWA / Offline / Field Scenarios

### Current State (Per Phase 7)

**Exists:**
- ✅ PWA framework integrated
- ✅ Bootstrap endpoint functional
- ✅ Runtime caching active

**Incomplete:**
- ❌ Limited offline-usable dictionaries
- ❌ Weak local draft persistence
- ❌ Poor offline queue UX
- ❌ No conflict resolution UX
- ❌ No retry/resume guidance
- ❌ No sync diagnostics for users

**Supported Field Scenarios:**
- ⚠️ Briefing/instruction mark (partial)
- ⚠️ Incident draft registration (partial)
- ⚠️ Checklist draft completion (partial)
- ⚠️ Task/comment capture (partial)
- ⚠️ Media/photo sync (partial)

**Status:** Framework present; practical field workflows underdeveloped.

---

## Operational UX Hardening Status

### Pages Ready for Enhancement (Not Rewrite)

- AdminPage
- ContractorsPage
- ReferencePage
- SettingsPage
- ActivitiesPage
- MedicalPage
- FireSafetyPage
- FireTrainingPage
- FireInspectionsPage
- InspectionChecklistsPage
- InspectionPlansPage
- InspectionPrepPackagesPage

**Needed for Each:**
- Add next actions
- Add blockers/readiness context
- Add better empty states
- Add bulk actions (if applicable)
- Add deep links
- Reduce visual clutter
- Move advanced controls to secondary menu
- Keep primary CTA obvious

**Status:** All candidates for UX hardening pass; not replacement.

---

## Test Coverage Assessment

| Layer | Status | Notes |
|-------|--------|-------|
| Backend unit tests | ✅ Existing | Some coverage; needs expansion for tenancy/authz |
| Backend integration tests | ⚠️ Partial | Key paths need verification |
| Frontend tests | ❌ Sparse | Permission/loading/error scenarios weak |
| Contract/E2E tests | ❌ Missing | Critical workflows need end-to-end verification |

---

## Key Takeaways

| Finding | Implication |
|---------|-------------|
| Archive is large and modular | Architecture is real, not mock; ready for hardening |
| Many files are very heavy | Refactoring ≠ rewrite; but consolidation needed |
| Pages use real snapshot APIs | Frontend is not a shell; UX maturity is the gap |
| Non-production paths embedded | Biggest enterprise blocker; must isolate/replace |
| PWA and offline foundation exist | Do not rebuild; extend and harden |
| Tenant/authz/audit inconsistent | Consistency pass required before scaling |
| Admin and workspaces missing | Critical for daily corporate operations |
| Document core strong but not unified | Centralization and orchestration needed |

---

## Risk Assessment for Deployment

### High Risk (Blocks Corporate Use)
- Non-production fallback paths indistinguishable from production
- Tenant context sometimes lost in background jobs
- Permission checks inconsistent
- No task/attention/blocker surfaces

### Medium Risk (Degraded Experience)
- Heavy files increase maintenance burden
- UX maturity incomplete on operational pages
- Admin diagnostics minimal
- Field scenarios partially supported

### Low Risk (Polish)
- Architecture mostly sound
- Core modules functional
- PWA framework in place
- Test foundation exists

---

## Recommended Next Phase

**Focus:** **Enterprise Consistency & Operational Maturity** (not feature expansion)

**Sequence:**
1. Consistency hardening (backend/frontend uniformity)
2. Tasks/attention/blockers/role workspaces
3. Document lifecycle centralization
4. Non-production fallback elimination
5. Data quality + readiness
6. Admin diagnostics + governance
7. Field/PWA operational hardening
8. Page UX maturity
9. Reliability/observability
10. Comprehensive test coverage

**Timeline Implication:** 8–12 weeks intensive work for senior full-stack engineer/platform hardening lead.

---

## Archive Metadata

- **Repository Size:** Large (56 routes, 75 pages, 302 test artifacts)
- **Language Stack:** Python (FastAPI) + TypeScript (Vue/Vite)
- **Deployment Model:** SaaS, tenant-aware, multi-role
- **Critical Domains:** OHS, Fire Safety, HSE, Compliance, EDO, CRM, Billing, Mobile/PWA
- **Audit Version:** Archive (19), March 24, 2026
