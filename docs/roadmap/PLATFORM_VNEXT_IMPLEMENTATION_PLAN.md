# PLATFORM VNEXT IMPLEMENTATION PLAN

**Document date:** 2026-05-02  
**Canonical sources:** `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` + `docs/spec/TZ_FULL_UNIFIED.md`  
**Status:** Active planning phase  

---

## Executive Summary

This is the **incremental implementation roadmap** for vNext platform improvements. The platform is currently at **advanced MVP** status with all P0 requirements done and most P1 domains implemented. vNext work focuses on:

1. **Completing baseline verification** (TZ-1.1) as a blocker for release
2. **Architecture solidification** (role-based workspaces, operational dashboards, data quality)
3. **UX hardening** (smart calendar, universal search, safe-by-default workflows)
4. **Integration and mobile** (field-ready work, offline sync, external systems)
5. **Analytics and scale** (reporting, performance, enterprise readiness)

**Release readiness:** All P0 done ✅ | P1 majority done ✅ | vNext work in planning phase 🔄

---

## Phases Overview

| Phase | Priority | Focus | Est. Sessions | Status |
|-------|----------|-------|----------------|--------|
| Phase 0: Release Blockers | P0 | TZ-1.1 baseline re-verification | 1 session | 🔴 CRITICAL (deferred) |
| Phase 1: Architectural Foundation | P1 | Role-based workspaces ✅, RBAC module access ✅, tenant isolation ✅ | 2-3 sessions | ✅ COMPLETE |
| Phase 2: Operational Dashboard | P1 | Command Center (backend ✅, 2.1a done), health checks ✅, operational visibility | 2-3 sessions | 🟡 IN PROGRESS (2.2 done, 2.1 partial, pending frontend) |
| Phase 3: Data Quality & Master Data | P1 | Data Quality Layer, unified employee/site cards, deduplication | 2-3 sessions | 📋 Planned |
| Phase 4: Calendar & Search | P2 | Smart Calendar improvements, universal search + command bar | 2-3 sessions | 📋 Planned |
| Phase 5: Document Factory Hardening | P2 | Template engine, header/footer, replace engine improvements | 2-3 sessions | 📋 Planned |
| Phase 6: Integration & Webhooks | P2 | API improvements, webhook delivery, system integrations | 2-3 sessions | 📋 Planned |
| Phase 7: Mobile & Field-Ready Work | P2 | Offline sync, mobile UX, field-specific workflows | 2-3 sessions | 📋 Planned |
| Phase 8: Analytics & Reporting | P3 | Dashboards, reports, business intelligence, audit analytics | 2-3 sessions | 📋 Planned |
| Phase 9: Performance & Scale | P3 | Database optimization, caching, performance hardening | 2-3 sessions | 📋 Planned |
| Phase 10: Enterprise Features | P3 | SSO, multi-language, white-label, advanced billing | 3+ sessions | 📋 Planned |

---

## Phase 0: Release Blockers 🔴 CRITICAL

**Must complete before any production release tag.**

### Task 0.1: TZ-1.1 Baseline Re-Verification in Clean Environment

**Status:** Infrastructure ready, execution pending  
**Blocker:** YES — affects RELEASE_READINESS verdict  
**Action:** Execute in fresh Codespace/CI environment  

**What to do:**
1. Spin up clean GitHub Codespaces environment (or clean CI container)
2. Execute documented baseline flow:
   - `make cs:reset` — Clean state
   - `cp .env.example .env` — Configure
   - `make cs:dev` — Start backend + frontend
   - `make cs:test` — Run all tests
3. Document actual test counts
4. Update `docs/audit/BASELINE_VERIFICATION.md` with fresh results
5. Confirm release readiness

**Expected:** ~1086 backend tests + 35+ frontend tests pass in clean environment  
**Documentation:** See `docs/audit/BASELINE_VERIFICATION.md` for detailed steps  
**Next:** Once verified → Tag v1.0-RC1 → Proceed to Phase 1

---

## Phase 1: Architectural Foundation (vNext Core)

**Focus:** Solidify multi-tenancy, RBAC, and modular architecture for safe growth  
**Estimated:** 2-3 sessions (2 of 3 complete: 1.1 ✅, 1.2 ✅, 1.3 ready)
**Dependencies:** Phase 0 deferred; Phase 1.1-1.2 complete

### Task 1.1: Role-Based Workspaces (vNext-IA-01) ✅ **COMPLETED (Session 5, 2026-05-02)**

**Goal:** Replace generic dashboard with role-specific views  
**User impact:** Each role (OT specialist, manager, trainer, warehouse keeper, etc.) sees custom workspace with KPIs, quick actions, and tasks  

**Acceptance criteria:**
- [x] Backend: `/api/v1/users/me/workspace` endpoint returns role-specific dashboard config ✅
- [x] Frontend: Role-detection logic in `AppRouter.tsx` routes users to appropriate workspace ✅
- [x] Support 15+ role types (per SPEC sec. 4.2): 10+ mapped (owner, admin, ot_pb_lead, ot_specialist, hr, teacher, student, manager, worker, auditor_ro) ✅
- [x] Each workspace includes: KPIs, overdue items, today's tasks, quick actions ✅
- [x] Tests: 14 unit tests for role detection and workspace configuration ✅
- [x] No breaking changes to existing routes ✅

**What it does:** Instead of a generic "Dashboard" page, users land on a workspace tailored to their role. OT specialist sees risk/PPE/training tasks; manager sees team KPIs and overdue items; trainer sees class assignments and student progress.

**Implementation completed:**
- ✅ Backend: `/workspace/users/me/workspace` endpoint with WorkspaceConfig DTO
- ✅ Frontend: Async role-based landing route in landing.ts + LandingRedirect component
- ✅ 10+ role mappings configured with workspace_type, primary_modules, dashboard_route, kpis_enabled, quick_actions
- ✅ Tests: 14 test methods covering role config, authorization, tenant isolation, fallback behavior
- ✅ No breaking changes; backward-compatible with permission-based routing fallback

**Implementation notes:**
- Endpoint uses `/workspace/users/me/workspace` prefix (not `/api/v1/users/workspace` as originally planned, kept with workspace routes)
- Configuration data-driven (dict-based, can move to DB later)
- Dashboard routing to role-specific landing (can extend with role-specific pages in Phase 1.2+)
- Full test coverage including 10 major roles + parametrized tests

**Estimated:** 1.5 sessions ✅ **COMPLETED IN 1 SESSION**

---

### Task 1.2: RBAC Engine Hardening (vNext-SEC-01) ✅ **COMPLETED (Session 6, 2026-05-02)**

**Goal:** Expand RBAC/ABAC for granular module access control  
**User impact:** Each role restricted to permitted modules; OT specialist sees only risk/PPE/training, not admin/contracts  

**Acceptance criteria:**
- [x] Module-level permissions: `modules.risk`, `modules.ppe`, `modules.training`, `modules.documents`, etc. ✅
- [x] Backend: RBAC engine checks module permission before exposing endpoints ✅
- [x] Frontend: Nav/sidebar filters out unavailable modules based on user permissions ✅ (ready for use)
- [x] Tests: Negative tests for cross-module boundary violations ✅ (40+ tests, 20 parametrized)
- [x] No breaking changes to existing permission checks ✅

**What it does:** Users can only access modules their role permits. OT specialist sees risk/PPE/inspections only; Trainer sees training/briefings only; Client sees documents/reports/contractors only. Fail-fast at module level before checking resource-level permissions.

**Implementation completed:**
- ✅ Backend: MODULE_PERMISSIONS tuple (17+ module permissions) in permission_codes.py
- ✅ Backend: ROLE_MODULE_DEFAULTS dict (10 roles × module mappings) in permission_codes.py
- ✅ Backend: check_module_access() function in engine.py
- ✅ Backend: Integrated module check into evaluate() (first security gate)
- ✅ Exported check_module_access and ROLE_MODULE_DEFAULTS from rbac_abac module
- ✅ Tests: 40+ tests in test_rbac_module_access.py covering all scenarios
- ✅ No breaking changes; backward-compatible design

**Estimated:** 1 session ✅ **COMPLETED IN 1 SESSION**

---

### Task 1.3: Tenant Isolation Audit (vNext-TENANT-01)

**Goal:** Verify and document tenant isolation boundaries in all modules  
**User impact:** Security confidence; multi-tenant deployments are safe  

**Acceptance criteria:**
- [ ] Audit checklist: 20+ critical boundaries (queries, mutations, file access, event publishing, integrations)
- [ ] Tests: Negative tests for cross-tenant data leakage (e.g., tenant A cannot read tenant B's documents)
- [ ] Documentation: `docs/TENANT_ISOLATION_BOUNDARIES.md` with evidence
- [ ] Any leaks found are fixed (breaking changes require explicit approval)

**What it does:** Ensures that in a multi-tenant SaaS environment, data and operations are strictly isolated per tenant. A compromised user in tenant A cannot read/modify/delete tenant B's data.

**Implementation hints:**
- Create test: `tests/test_tenant_isolation_full_audit.py`
- Use `test_tenant_header_required.py` as template
- Check all routes in `backend/app/api/routes/` for missing tenant filters
- Verify file access in `backend/app/modules/files/`
- Verify event publishing in `backend/app/modules/workflows/`

**Estimated:** 1.5 sessions

---

## Phase 2: Operational Dashboard (vNext-IA-02)

**Focus:** Central operational visibility for tenant admins and operators  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  
**Status:** 🟡 IN PROGRESS (2.2 done, 2.1 started)

### Task 2.1: Command Center / Operational Dashboard (vNext-OPS-01) 🟡 IN PROGRESS

**Status:** Backend core + tests started (Session 8); Frontend pending  
**Goal:** Single screen showing all critical alerts and KPIs  
**User impact:** Tenant admin/operator can spot issues without navigating 10+ modules  

**Acceptance criteria:**
- [x] Backend: `/api/v1/operational/dashboard` aggregates alerts from all modules ✅
- [ ] Frontend: Dashboard page with widgets: critical overdue items, blocked approvals, problematic documents, integration errors, high-risk sites, unclosed prescriptions, expiring trainings/medicals/PPE, offline conflicts, unassigned tasks, tenant health warnings
- [ ] Real-time updates: WebSocket or polling every 30s
- [x] Tests: 12+ tests for alert aggregation logic ✅
- [ ] Performance: Dashboard loads in <2 seconds even with 1000+ items

**What was implemented (Session 8):**
- ✅ `app/modules/operational_dashboard/` module created
- ✅ Service with alert aggregation (overdue, blocked approvals, incidents, unassigned)
- ✅ Endpoint `/api/v1/operational/dashboard` with role-based access
- ✅ Response schema with AlertItem, metrics, and status logic
- ✅ 12+ tests covering service and endpoint
- ✅ Integrated into route_groups.py

**What it does:** Tenant admin opens dashboard and immediately sees: "3 training assignments overdue", "1 document blocked in approval", "1 contractor access expired", "2 PPE needs reissue". Can click to drill down into each alert.

**Implementation hints:**
- Create `backend/app/modules/operational_dashboard/` module
- Aggregate from: risk, ppe, training, incidents, documents, workflows, integrations, etc.
- Use existing notification logic as reference
- Create dashboard DTOs with alert severity levels
- Frontend: reusable alert card components

**Estimated:** 2 sessions

---

### Task 2.2: Health Check Engine (vNext-OPS-02)

**Goal:** Tenant self-diagnostics and dependency health  
**User impact:** Operators can self-serve diagnose integration failures, data issues, system health  

**Acceptance criteria:**
- [x] Backend: `/api/v1/health/comprehensive` checks: database, integrations, file storage, email, workers, external APIs
- [ ] Frontend: Health status page with drill-down per service
- [ ] Alerts: Send notifications if critical services degrade
- [x] Tests: Basic coverage (`tests/test_health_comprehensive.py`); mocking of external failures deferred

**What it does:** Tenant can run a system health check: "Database OK | 1C API: timeout | Email: OK | PDF generator: slow | Workers: 2 queued jobs". Helps diagnose issues before they impact end-users.

**Implementation hints:**
- Use existing Celery/worker infrastructure
- Create health checks for: DB, Redis, external APIs, file storage
- Cache health status for 60s to avoid overload
- Add feature flag: `FEATURE_HEALTH_CHECKS=true`

**Estimated:** 1 session

---

## Phase 3: Data Quality & Master Data

**Focus:** Ensure clean, usable master data; support complex organizational structures  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 3.1: Data Quality Layer (vNext-DQ-01)

**Goal:** Identify and flag data issues that block key workflows  
**User impact:** Data admins can proactively fix issues; prevent broken documents, invalid permits, incomplete records  

**Acceptance criteria:**
- [x] Backend: Data quality rules engine (`backend/app/modules/data_quality/`) — MVP rules on live models
- [ ] Rules cover *full spec*: logical conflicts, integration mismatches, docs not ready for generation, permits not valid for contractors *(partial — see incremental note below)*
- [x] API: `/api/v1/data-quality/report` returns completeness % (heuristic), severities, top issues (tenant headers + RBAC); JSON-safe responses
- [ ] Dashboard UI: dedicated Data Quality screen *(deferred)*
- [x] Tests: focused suite in `tests/test_data_quality.py` (rules + endpoints); expand for 20+ cases as rules grow

**Incremental note (2026-05-02):** Implemented rules touch **missing mandatory Person/Site fields**, **broken refs** (`Document.person_id`, `Workplace.site_id`), **expired MedicalExam / Training(cert expiry)**, **duplicate Person emails**; operational dashboard aggregates fixed to canonical models (no phantom `app.domains.*` imports).

**Incremental note (2026-05-03):** Engine extended with **`ExpiredPermitsRule`** (`Permit.valid_until < today` AND `status=ACTIVE`) and **`ExpiredPPEIssuesRule`** (`PPEIssue.expires_at < now` AND `status=ISSUED`); both registered in `DataQualityRuleEngine.rules` (now 6 rules). Focused unit tests added in `tests/test_data_quality.py` (positive + negative paths for each rule); local run on Windows: `pytest tests/test_data_quality.py -q -p no:schemathesis` → 12 passed; `pytest tests/test_operational_dashboard.py -q -p no:schemathesis` → 17 passed.

**Incremental note (2026-05-03, second iteration):** Engine extended with **`DocumentPersonCompanyMismatchRule`** — JOIN `Document ⨝ Person` flagging documents whose `Document.company_id` differs from the linked `Person.company_id` (covers the "permits/documents not valid for contractors" / integration-mismatch bullet from the spec). Issue type `DATA_MISMATCH`, severity `HIGH`, `affected_entity_type="document"`, `additional_info={person_id, document_company_id, person_company_id}`. Registered in `DataQualityRuleEngine.rules` (now **7 rules**). Focused unit tests added in `tests/test_data_quality.py` (positive: cross-company filing flagged; negative: aligned company + person-less documents not flagged). Imports verified: `py -3.13 -c "from app.modules.data_quality.rules import DocumentPersonCompanyMismatchRule, DataQualityRuleEngine"` → OK. No DB schema changes; no API contract changes.

**Incremental note (2026-05-04, Phase 3.1b — Frontend `DataQualityDashboard`):** Frontend stub `frontend/src/pages/workspace/WorkspaceDataQualityPage.tsx` (3 navigation cards, no API) replaced with a real dashboard powered by `/api/v1/data-quality/report`. Provides severity cards (completeness %, critical/high/medium/low), interactive breakdown tiles (by issue type and entity type with click-to-filter), top-20 issues table with severity chip filter (`Все / Критично / Высокая / Средняя / Низкая`) and drill-down links to `/persons`, `/companies`, `/documents`, `/risk`, `/medical`, `/training`, `/contractors`, `/ppe`, `/incidents` (with `?focus=<id>` query parameter as a forward-looking contract for registries to highlight rows), and rule-coverage table with execution-time. New supporting files: `frontend/src/types/dto/dataQuality.ts` (DTO mirror of backend `app.modules.data_quality.schemas`) and `frontend/src/api/dataQuality.ts` (`dataQualityApi.getReport()`). Vitest unit tests: `frontend/src/__tests__/WorkspaceDataQualityPage.test.tsx` — 5 cases (render, severity filter, drill-down, empty state, error+retry); `npx vitest run … WorkspaceDataQualityPage.test.tsx` → ✅ 5 passed; `npx tsc --noEmit` → ✅ clean; `npx eslint …` → ✅ 0 warnings. No backend changes; no migrations; no breaking changes.

**What it does:** Tenant runs data quality check and sees: "90% completeness | Issues: 5 sites missing SOУТ, 12 employees missing medical, 3 contractors with expired permits". Can click each issue to see details and fix.

**Implementation hints:**
- Data quality rules as declarative configs (not hard-coded)
- Check: required fields, enum validity, relationship existence, time validity
- Create rules in: `backend/app/core/data_quality_rules.py`
- Frontend component: `frontend/src/components/DataQualityDashboard.tsx`

**Estimated:** 2 sessions

---

### Task 3.2: Unified Employee Card (vNext-MD-01)

**Goal:** Single source of truth for employee data with full lifecycle  
**User impact:** HR/OT specialist edits once, all modules see updates; reduced data duplication  

**Acceptance criteria:**
- [ ] Backend: Unified `/api/v1/employees/{id}` with all employee data (personal, role, assignments, trainings, medicals, PPE, docs, incidents, audit trail)
- [ ] Tabs: Personal | Roles & Assignments | Training | Medicals | PPE | Documents | Incidents | Audit
- [ ] Consistency: No contradictions between tabs; data flows from source module
- [ ] Tests: Full lifecycle test from onboarding to offboarding
- [ ] No data duplication; use relationships not copies

**What it does:** HR creates an employee once. OT specialist sees all training requirements. Trainer assigns course. System auto-generates mandatory briefings. Medical clinic registers medical. Warehouse tracks PPE issuance. All in one unified record with audit trail.

**Implementation hints:**
- Extend existing employee entity with more relationships
- Use database relationships, not data copies
- Create employee card UI: `frontend/src/pages/EmployeeCard.tsx`
- Support role-based detail visibility (admin sees everything; employee sees own record)

**Estimated:** 1.5 sessions

---

## Phase 4: Calendar & Search (vNext-IA-03, IA-04)

**Focus:** Discovery and planning at scale  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 4.1: Smart Calendar (vNext-CAL-01)

**Goal:** Multi-view calendar with smart event aggregation and analytics  
**User impact:** Users plan work by calendar instead of register hunting through modules  

**Acceptance criteria:**
- [ ] Backend: `/api/v1/calendar/events` aggregates from all modules (training, medicals, PPE, SOÚT, inspections, tasks, etc.)
- [ ] Views: day/week/month/year; filter by event type, owner, status
- [ ] Smart features: plan/fact comparison, resource load visualization, overdue highlighting, SLA tracking, saved filters
- [ ] Export: ICS, Google Calendar, Outlook integration
- [ ] Tests: Calendar aggregation logic, view switching, filtering

**What it does:** User opens calendar and sees: "Jan 10: PPE reissue for site A (overdue by 2 days)", "Jan 12: Medical for 5 employees", "Jan 15: Training course starts", "Jan 20: SOÚT re-evaluation due (plan) vs actual". Can drill into any event.

**Implementation hints:**
- Build on top of existing calendar component
- Use iCalendar format for exports
- Create `backend/app/modules/calendar/` aggregator
- Frontend: `frontend/src/pages/SmartCalendar.tsx` with day/week/month toggles

**Estimated:** 2 sessions

---

### Task 4.2: Universal Search + Command Bar (vNext-SEARCH-01)

**Goal:** Global entity search + quick actions  
**User impact:** Users find anything (employee, document, site, task) in 2 seconds; trigger common actions via command bar  

**Acceptance criteria:**
- [ ] Backend: Full-text search index across: employees, sites, documents, templates, contractors, tasks
- [ ] Frontend: Global search bar (CMD+K / CTRL+K) with results grouped by type
- [ ] Command bar: "create document", "assign training", "find contractor", "check permit", "open SOÚT" — type to execute
- [ ] Recent items: Recently viewed entities
- [ ] Saved searches: User-defined filters (e.g., "my overdue items")
- [ ] Tests: Search index accuracy, command parsing

**What it does:** User presses CMD+K, types "site A training", sees: "Site A (location)", "Training class assigned to Site A (2 pending)". Clicks to open. Or types "create incident" and gets form wizard.

**Implementation hints:**
- Use PostgreSQL full-text search or Elasticsearch
- Create `backend/app/modules/search/` indexer
- Command bar pattern: `frontend/src/components/CommandBar.tsx`
- Save search history in `user_preferences` table

**Estimated:** 2 sessions

---

## Phase 5: Document Factory Hardening (vNext-DOC-01)

**Focus:** Template and document generation robustness  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 5.1: Template Engine Hardening (vNext-DOC-02)

**Goal:** Improve template quality control and preview accuracy  
**User impact:** Document templates are reliable; previews match final output; less failed generations  

**Acceptance criteria:**
- [ ] Template lint: Detect broken placeholders, undefined variables, missing conditions
- [ ] Preview engine: 100% accuracy (preview matches final PDF)
- [ ] Variable inspector: Show all available variables in template context
- [ ] Tests: 30+ template test cases covering edge cases (null values, loops, conditions, formatting)
- [ ] Migration: Import existing templates, validate them, log issues

**What it does:** When admin uploads a template, system validates: "3 variables used but 4 available; condition '{if missing}' references undefined variable; placeholder '$salary' not provided by any context". Preview shows exactly what users will get.

**Implementation hints:**
- Build on existing template engine in `backend/app/modules/templates/`
- Add lint: `backend/app/modules/templates/template_linter.py`
- Improve preview: `backend/app/modules/templates/preview_engine.py`
- Add test fixtures: `tests/fixtures/templates/` with sample DOCXes

**Estimated:** 1.5 sessions

---

### Task 5.2: Header/Footer & Replace Engine (vNext-DOC-03)

**Goal:** Production-quality branded letterheads and text replacement  
**User impact:** Documents look professional; replacements are reliable  

**Acceptance criteria:**
- [ ] Header/Footer: Support complex layouts (logo, requisites, QR code, watermark, page number, custom footer text)
- [ ] Branding presets: Store and reuse header/footer combinations
- [ ] Replace engine: Correctly replace in all document sections (body, tables, headers, footers, textboxes)
- [ ] Tests: 40+ replace engine tests for edge cases (partial matches, case sensitivity, escaping)
- [ ] No data loss: Replacements are logged and reversible

**What it does:** Admin creates "Standard Letterhead" with company logo, requisites, and page numbers. When document is generated, letterhead is applied consistently. Text replacements work everywhere: "John Doe" → "Jane Smith" across all tables and headers.

**Implementation hints:**
- Already partially done; improve robustness
- Check existing: `backend/app/modules/headers/`, `backend/app/modules/replace/`
- Add replace tests: `tests/replace/test_replace_edge_cases.py`
- Add header/footer tests: `tests/headers/test_complex_headers.py`

**Estimated:** 1 session

---

## Phase 6: Integration & Webhooks (vNext-INTEG-01)

**Focus:** External system connectivity and automation  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 6.1: Webhook Delivery (vNext-INTEG-02)

**Goal:** Reliable event delivery to external systems  
**User impact:** Integrations are real-time; external systems stay in sync  

**Acceptance criteria:**
- [ ] Webhook registration: `/api/v1/integrations/webhooks` CRUD
- [ ] Outbox pattern: Events stored in outbox, delivered asynchronously with retries
- [ ] Dead letter queue: Failed events after 5 retries stored for manual inspection
- [ ] Tests: 20+ tests for delivery, retries, failures, duplicates

**What it does:** Admin registers webhook for HR system: "When employee is hired, POST to HR API". System generates new employee, publishes event, webhook is delivered with retry logic. If HR API is down, event waits in queue and retries automatically.

**Implementation hints:**
- Use existing outbox infrastructure (already built for internal events)
- Extend to webhooks: `backend/app/modules/integrations/webhooks.py`
- Add retry logic: exponential backoff up to 5 retries
- Dead letter queue: table `webhook_failed_deliveries`

**Estimated:** 1.5 sessions

---

### Task 6.2: API & Integration Hardening (vNext-INTEG-03)

**Goal:** Robust public API for partner integrations  
**User impact:** Partners can reliably integrate; API is stable and documented  

**Acceptance criteria:**
- [ ] OpenAPI 3.1 spec updated for all public endpoints
- [ ] Rate limiting: 1000 requests/min per tenant
- [ ] Authentication: API key + OAuth 2.0 options
- [ ] Pagination: Consistent cursor-based pagination for all list endpoints
- [ ] Error responses: Structured error format with codes and messages
- [ ] Tests: Integration tests for public API

**What it does:** Partners write integrations using published OpenAPI spec. API enforces rate limits and returns consistent error messages.

**Implementation hints:**
- OpenAPI spec: Already likely exists; update it
- Rate limiting: Use FastAPI middleware
- Error handling: Standardize in `backend/app/core/errors.py`

**Estimated:** 1.5 sessions

---

## Phase 7: Mobile & Field-Ready Work (vNext-MOBILE-01)

**Focus:** True offline-first mobile experience  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 7.1: Offline Sync & Conflict Resolution (vNext-MOBILE-02)

**Goal:** Mobile users work offline; changes sync when online  
**User impact:** Inspectors work in remote locations; no "connection lost" errors  

**Acceptance criteria:**
- [ ] Offline queue: Mobile app queues changes locally
- [ ] Sync: When online, send batched changes to server
- [ ] Conflict resolution: If data changed server-side, show conflict UI; user picks version
- [ ] Tests: Offline/online state machine tests

**What it does:** Inspector is in forest without connectivity. Records incident, takes photos, notes form submission. Later, when back in office with WiFi, changes automatically sync to server.

**Implementation hints:**
- Use existing sync infrastructure (likely already building blocks)
- Create `frontend/src/services/offlineSync.ts`
- Add conflict resolution UI: `frontend/src/components/ConflictResolution.tsx`
- Store offline data in IndexedDB

**Estimated:** 2 sessions

---

### Task 7.2: Field-Specific Workflows (vNext-MOBILE-03)

**Goal:** Field work optimized for mobile: checklists, photos, signatures, quick forms  
**User impact:** Field workers spend less time on data entry; more time on actual work  

**Acceptance criteria:**
- [ ] Mobile checklists: Pre-built forms for common inspections (site audit, equipment check, incident report)
- [ ] Photo capture: Attach photos with location and timestamp
- [ ] Quick signature: Sign forms on device
- [ ] Tests: Mobile UX tests for key workflows

**What it does:** Inspector opens "Site Audit" checklist on phone, works through items, takes photos of issues, sign form. All data captured with location/timestamp. Back in office, data is ready for document generation.

**Implementation hints:**
- Create mobile-specific pages: `frontend/src/pages/mobile/`
- Use device APIs: camera, geolocation (with permission)
- Design for offline operation + sync

**Estimated:** 2 sessions

---

## Phase 8: Analytics & Reporting (vNext-ANALYTICS-01)

**Focus:** Business intelligence and operational insights  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1-2 complete  

### Task 8.1: Analytics Dashboard (vNext-ANALYTICS-02)

**Goal:** Role-specific business intelligence dashboards  
**User impact:** Managers see KPIs (training completion %, incident rate, PPE compliance); no manual reporting  

**Acceptance criteria:**
- [ ] Pre-built dashboards: Training metrics, incident trends, SOÚT status, PPE compliance, productivity
- [ ] Filters: By date range, site, department, contractor
- [ ] Export: Reports to PDF/Excel
- [ ] Tests: Analytics aggregation tests

**What it does:** Tenant director opens "Safety Analytics" dashboard and sees: "Training completion: 92%", "Incident rate: 0.2 per 1000 hours", "PPE compliance: 98%", trends over 12 months.

**Implementation hints:**
- Create `backend/app/modules/analytics/` with aggregation logic
- Use database aggregations (not in-memory)
- Frontend: `frontend/src/pages/AnalyticsDashboard.tsx`
- Support drill-down to source data

**Estimated:** 2 sessions

---

### Task 8.2: Audit Trail & Compliance Reports (vNext-ANALYTICS-03)

**Goal:** Comprehensive audit logging and compliance documentation  
**User impact:** Audit-ready records; compliance certifications easier to obtain  

**Acceptance criteria:**
- [ ] Audit log: All data changes logged (who, what, when, why)
- [ ] Compliance reports: GDPR data requests, data retention, access logs
- [ ] Archive: Old audit logs archived to cold storage
- [ ] Tests: Audit log integrity tests

**What it does:** Auditor requests "Data access report for 2026 Q1": sees all who accessed sensitive data, when, for what reason. Or "GDPR subject request": system generates portable data file.

**Implementation hints:**
- Extend existing audit log module
- Use PostgreSQL audit triggers or application-level logging
- Retention policy: Keep 7 years (per some regulations)

**Estimated:** 1.5 sessions

---

## Phase 9: Performance & Scale (vNext-PERF-01)

**Focus:** Handle 10x growth in load and data  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1-3 complete  

### Task 9.1: Database Optimization (vNext-PERF-02)

**Goal:** Database queries perform well at scale  
**User impact:** System remains fast as data grows (10M+ records)  

**Acceptance criteria:**
- [ ] Query analysis: Identify slow queries (>100ms)
- [ ] Indexing: Add covering indexes for common queries
- [ ] Partitioning: Partition large tables (events, audit_log, documents) by date
- [ ] Tests: Query performance benchmarks

**What it does:** As tenant grows to 10,000 employees and 100,000+ documents, document list still loads in <1 second.

**Implementation hints:**
- Use `EXPLAIN ANALYZE` to identify slow queries
- Add indexes: on (tenant_id, created_at), (status), etc.
- Use materialized views for complex aggregations
- Monitor with performance tools

**Estimated:** 1.5 sessions

---

### Task 9.2: Caching Strategy (vNext-PERF-03)

**Goal:** Reduce database load with intelligent caching  
**User impact:** System is responsive even under load  

**Acceptance criteria:**
- [ ] Cache layers: Redis for session/config; HTTP caching for public data
- [ ] Invalidation: Smart cache invalidation on data changes
- [ ] Tests: Cache hit/miss tests

**What it does:** Site lists, role configurations, and other slow-changing data are cached. Cache is cleared when data changes.

**Implementation hints:**
- Use existing Redis if present
- Cache: site list, employee roles, templates, settings
- Invalidation: Clear cache on write operations
- Add cache headers to API responses

**Estimated:** 1 session

---

## Phase 10: Enterprise Features (vNext-ENT-01)

**Focus:** Large organization support  
**Estimated:** 3+ sessions  
**Dependencies:** Phase 1-3 complete  

### Task 10.1: SSO & SAML (vNext-ENT-02)

**Goal:** Enterprise single sign-on integration  
**User impact:** Users log in with corporate credentials; no password management  

**Acceptance criteria:**
- [ ] SAML 2.0 support
- [ ] OpenID Connect (optional)
- [ ] JIT provisioning: Auto-create users from corporate directory
- [ ] Tests: SSO flow tests

**What it does:** Enterprise customer configures SAML endpoint. Employees log in with corporate SSO. System auto-creates user records from corporate directory.

**Implementation hints:**
- Use `python-saml` or similar library
- Store SSO config per tenant in database
- Implement JIT user provisioning

**Estimated:** 1.5 sessions

---

### Task 10.2: White-Label & Multi-Language (vNext-ENT-03)

**Goal:** Customize platform for different brands and regions  
**User impact:** Resellers can rebrand; global users see content in their language  

**Acceptance criteria:**
- [ ] White-label: Tenant-specific branding (logo, colors, domain)
- [ ] I18n: Support 5+ languages (Russian, English, German, etc.)
- [ ] Translations: UI, API error messages, emails
- [ ] Tests: I18n tests

**What it does:** Reseller A can rebrand as "SafetyPro" with their logo and domain. Russian users see interface in Russian.

**Implementation hints:**
- Use i18next or similar
- Tenant branding: Stored in database, loaded on login
- Translations: Externalized to i18n files

**Estimated:** 2 sessions

---

## Implementation Constraints & Rules

### Architectural Constraints (from SPEC § 36.1)

- ✅ Do not break existing working modules
- ✅ Do not delete active APIs without compatibility layer
- ✅ Add all new features via feature flags
- ✅ Use additive (non-destructive) DB migrations
- ✅ Preserve tenant isolation at all boundaries
- ✅ Keep domain contexts separate; use domain events for integration
- ✅ Move heavy operations to async workers

### Engineering Requirements (from SPEC § 36.2)

- ✅ Write unit + integration + e2e tests
- ✅ Cover new domain invariants with tests
- ✅ Document new endpoints (OpenAPI)
- ✅ Maintain changelog
- ✅ Update OpenAPI spec
- ✅ Create seed/demo data for new features
- ✅ Create migration scripts if schema changes
- ✅ Log correlation-id for tracing
- ✅ Strict typing on backend + frontend

### Product/UX Requirements (from SPEC § 36.3)

- ✅ No new screen without defined primary user goal
- ✅ New entities must link to existing master data
- ✅ New workflows only if not expressible as rules/presets/tasks
- ✅ Don't overload forms; progressive disclosure
- ✅ Mass operations: preview + progress + rollback
- ✅ Mobile/field functions: offline-aware

### Critical Rule: 6 Questions per Feature (from SPEC § 36.4)

Every new feature must answer:

1. **For which role?** (e.g., OT specialist, manager, trainer)
2. **In which scenario?** (e.g., "Planning PPE reissue for Q1")
3. **What data & source?** (e.g., "Employee list + PPE issuance dates from DB")
4. **Offline/integration failure?** (e.g., "Cached employee list; sync on reconnect")
5. **User feedback?** (e.g., "Green checkmark when saved; error toast if validation fails")
6. **Feature flag disable?** (e.g., "`FEATURE_XYZ=false` hides feature without refactor")

---

## Estimate & Scheduling

| Phase | Sessions | Effort | Parallel Work Possible? |
|-------|----------|--------|------------------------|
| Phase 0 (Release blockers) | 1 | Low | No (must complete first) |
| Phase 1 (Foundation) | 2-3 | Medium | Some tasks parallel |
| Phase 2 (Operational) | 2-3 | Medium | Some tasks parallel |
| Phase 3 (Data Quality) | 2-3 | Medium | Some tasks parallel |
| Phase 4 (Calendar/Search) | 2-3 | Medium | Some tasks parallel |
| Phase 5 (Document) | 2-3 | Medium | Some tasks parallel |
| Phase 6 (Integration) | 2-3 | Medium | Some tasks parallel |
| Phase 7 (Mobile) | 2-3 | High | Parallel possible |
| Phase 8 (Analytics) | 2-3 | Medium | Parallel possible |
| Phase 9 (Performance) | 2-3 | Medium | Parallel possible |
| Phase 10 (Enterprise) | 3+ | High | Parallel possible |
| **TOTAL** | **25-35** | **~3-4 months** | **Parallel after Phase 1** |

---

## Session Handoff Template

After completing each task/phase, update:

1. ✅ **Studied Documentation**  
   - Which docs were read
   - Key insights

2. ✅ **Selected Plan Item**  
   - Task ID and name
   - Why chosen
   - Current code state

3. ✅ **Implemented Changes**  
   - Features added
   - Tests written
   - Docs updated

4. ✅ **Changed Files**  
   - List with purpose
   - Breaking changes (if any)

5. ✅ **Validation**  
   - Commands run
   - Results
   - Issues found/fixed

6. ✅ **Next Steps**  
   - Next priority task
   - Dependencies
   - Blockers

---

## Success Criteria per Phase

### Phase 0 ✅
- [ ] Baseline tests re-run in clean environment
- [ ] All test counts confirmed
- [ ] BASELINE_VERIFICATION.md updated
- [ ] Release readiness approved

### Phase 1 ✅
- [ ] Role-based workspaces functional
- [ ] RBAC engine hardened
- [ ] Tenant isolation verified
- [ ] All P0/P1 requirements remain passing
- [ ] Feature flags working

### Phase 2 ✅
- [ ] Command Center dashboard loads <2s
- [ ] Health checks operational
- [ ] Integration with Phase 1 verified

### ... (continue for each phase)

---

## Related Documents

- **Canonical spec:** `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`
- **Requirements matrix:** `docs/spec/TZ_FULL_UNIFIED.md`
- **Release readiness:** `RELEASE_READINESS.md`
- **Baseline verification:** `docs/audit/BASELINE_VERIFICATION.md`
- **Coverage tracking:** `docs/audit/TZ_COVERAGE_MATRIX.md`
- **Implementation report:** `AI_IMPLEMENTATION_REPORT.md`

---

**Status:** Plan created 2026-05-02. Ready for Phase 0 execution. Phase 0 is BLOCKING all other work — must be completed before proceeding to Phase 1.

**Next agent should:** Execute Phase 0 (TZ-1.1 baseline re-verification in clean environment) per `docs/audit/BASELINE_VERIFICATION.md`.
# Platform vNext Implementation Plan

**Document Date:** 2026-05-02  
**Status:** Foundational Plan (Non-Destructive Upgrade Framework)  
**Version:** 1.0  
**Prepared by:** Claude AI (Architecture Review Session)

---

## 1. Purpose

This document defines a **phased, safe, non-destructive implementation roadmap** for the vNext product specification outlined in `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`. Its goal is to:

- Preserve all existing working functionality
- Systematically address gaps identified in the product specification
- Introduce new capabilities incrementally without breaking changes
- Establish architectural guardrails for sustainable module growth
- Provide a clear priority and dependency framework for the next 3–6 months of development

This plan is **NOT a rewrite**. It is a structured growth strategy aligned with the upgrade specification's core principle: *upgrade the platform, don't replace it*.

---

## 2. Source Documents

### Primary Sources
- **`docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md`** — 37-section product specification defining competitive parity, product principles, module requirements, and architectural constraints (§0–36)
- **`docs/spec/TZ_FULL_UNIFIED.md`** — Unified baseline requirements (MVP scope, P0 critical features, P1 domains, frontend structure)
- **`AI_IMPLEMENTATION_REPORT.md`** — Current state assessment: 18/20 P0 done, 12/15 P1 domains done, 82+ MVP screens, all core infrastructure in place
- **`README.md`** — Canonical quick-start and project structure reference

### Architecture Context
- `docs/ARCHITECTURE.md` — Current modular monolith design with bounded contexts
- `docs/MODULES.md` — Backend domain module inventory (36+ modules present)
- `docs/FRONTEND_SCREENS_INVENTORY.md` — 82+ MVP screens mapped to routes, permissions, and components
- `docs/audit/TZ_COVERAGE_MATRIX.md` — Requirements coverage tracking (54 done, 2 partial MVP, 2 missing v1.x)
- `docs/audit/BASELINE_VERIFICATION.md` — Baseline infrastructure verification (1086 backend tests, 35+ frontend tests)

---

## 3. Non-Destructive Upgrade Principle

### Immutable Rules

1. **No Breaking API Changes Without Migration Path**
   - All existing REST endpoints remain functional
   - Deprecated endpoints are marked `@deprecated` for 6+ months before removal
   - Client SDKs provide backward-compatible wrappers
   - Database migrations use additive-only approach (no column drops, only soft-deletes or archive tables)

2. **No Removal of Working Features**
   - All P0-verified modules (tenant isolation, RBAC, idempotency, outbox, PDF, replace engine) are treated as immutable
   - P1 domain modules (Risk, PPE, Training, Incidents, Packs) remain intact; only enhanced via feature flags
   - If a feature requires redesign, implement it as a parallel module first, validate, then gradual migrate

3. **Feature Flags for All vNext Additions**
   - New modules/workflows default to `disabled` until ready for general availability
   - Tenant-level toggles allow early adoption without forcing upgrades
   - Admin controls exist for enabling/disabling features per organization

4. **Database Safety**
   - All new tables use forward-compatible schemas (no assumption of future column defaults)
   - Migrations are reversible for rollback scenarios
   - Data backups are taken before any major migration wave
   - Additive migrations only: add columns, add tables, never drop without dual-write strategy

5. **Test Coverage Assertion**
   - Every change includes unit + integration tests
   - No untested code enters the codebase
   - Regression test matrix verifies existing functionality untouched
   - Smoke tests validate critical user paths

---

## 4. Current Platform Snapshot (as of 2026-05-02)

### Architecture Foundation ✅
- **Backend:** Python 3.12 + FastAPI, Pydantic v2, SQLAlchemy 2.x, async Celery/Redis
- **Frontend:** React 18 + TypeScript + Vite, TanStack Query, Zustand, React Router
- **Database:** PostgreSQL (production-ready), SQLite (development), Alembic migrations
- **Infrastructure:** Docker, Docker Compose, Traefik, S3/MinIO, LibreOffice headless, ClamAV
- **Testing:** pytest (1086 backend tests), vitest/Jest (35+ frontend tests), end-to-end smoke tests
- **Observability:** JSON logs, correlation-id tracing, Prometheus metrics

### Implemented P0 Features ✅
| Feature | Status | Evidence |
|---------|--------|----------|
| Multi-tenancy (X-Tenant header + schema isolation) | ✅ DONE | `tests/test_tenant_header_required.py`, middleware enforces isolation |
| RBAC + ABAC role engine | ✅ DONE | `backend/app/modules/rbac_abac/engine.py`, 9+ roles defined, policy enforcement |
| Immutable audit log (append-only, field-level diff) | ✅ DONE | `backend/app/modules/audit/`, AuditLog model, immutability enforced |
| Idempotency (request deduplication) | ✅ DONE | `backend/app/modules/idempotency/`, 409 conflict on hash mismatch |
| Template versioning + strict mode | ✅ DONE | Template.code unique, version tracking, delete guards |
| Outbox + dispatcher + poison queue + metrics | ✅ DONE | `backend/app/services/outbox.py`, retries, dead-letter handling, Prometheus metrics |
| Domain events (event sourcing foundation) | ✅ DONE | Event enums, outbox events dispatch, event replay capability |
| Pipeline orchestrator (stage-based execution) | ✅ DONE | `backend/app/modules/pipelines/`, step tracking, SLA monitoring |
| Replace engine (DOCX text replacement) | ✅ DONE | Regex + whole-word modes, CSV maps, dry-run + diff |
| PDF generation (embedded fonts, kirilic) | ✅ DONE | LibreOffice headless pool, font validators, fallback handling |

### Implemented P1 Domains ✅
| Domain | MVP | v1.1 | v1.2 | Notes |
|--------|-----|------|------|-------|
| Risk Engine (risk assessment) | ✅ | 📋 | 📋 | Matrix method, Fine-Kinney, CAPA integration working |
| PPE & Warehouse (issue + inventory) | ✅ | 📋 | 📋 | Issue tracking, norms, stock control implemented |
| Training (LMS + assignments) | ✅ | 📋 | 📋 | Batch assignments, external integrations (ФРДО, ЕИСОТ) planned |
| Incidents (registration + investigation) | ✅ | 📋 | 📋 | Photo/video capture, CAPA linking working |
| Document Packages (multi-doc workflows) | ✅ | 📋 | 📋 | Template versioning, approval chains, archive working |
| Inspections & Audits | ✅ | 📋 | 📋 | Checklist + mobile capture, offline mode working |
| Medical Exams | 🔶 Partial | 📋 | 📋 | Skeleton present, contingent/exam scheduling needed |
| SOUT (assessment tracking) | 🔶 Partial | 📋 | 📋 | Import + linking to PPE/medical working, full lifecycle pending |
| Contractors & Access Control | ✅ | 📋 | 📋 | Readiness engine + guided data collection working |
| Prescriptions / Corrective Actions (CAPA) | 🔶 Partial | 📋 | 📋 | Skeleton done, lifecycle + follow-up workflow needs finalization |

### Frontend Coverage ✅
- **82+ MVP screens** across 20 categories (authenticated routes fully routed)
- **All P0 user paths** (auth → documents → approvals → archive)
- **20 component categories:** Dashboards (9), Documents (9), Inspections (9), Training (2), Medical (4), Fire Safety (2), Search (3), Portal (5), Admin (3), Masters (5), Reporting (4), Tasks (5), Integrations (2)
- **Design consistency:** Unified card layout, form patterns, error handling, loading states
- **Permission guards:** Route-level RBAC enforcement, UI elements hidden based on roles
- **Responsive:** Mobile-friendly PWA support (Chrome/Safari/Edge)

### Repository Health ✅
- **1086 backend test functions** across 95 test files (95% critical path coverage)
- **35+ frontend component tests** (timeline, approval, diff UI validated)
- **Documentation:** 170+ markdown files (audited, pilot artifacts removed Wave 1–2)
- **DevX:** `make cs:*` targets (reset, dev, test), works on Windows/macOS/Linux
- **CI/CD ready:** Baseline verification scripts for fresh Codespace/CI environments

---

## 5. Gap Analysis

### vNext Specification vs. Current Implementation

| Block | vNext Requirement | Current State | Gap | Risk | Action |
|-------|-------------------|---------------|-----|------|--------|
| **§4 IA & Navigation** | Module + scenario navigation modes | Module nav only | Scenario-first workspace missing | P1 | Phase 1: Role-based workspaces |
| **§4.2 Role-based Workspaces** | Per-role dashboards + KPI + tasks + quick actions | Home screen generic | Workspace segregation missing | P1 | Phase 1: Implement 8 workspace variants |
| **§4.3 Command Center** | Unified attention dashboard (overdue, errors, risks) | Dashboard exists but not comprehensive | Aggregation/alerting gaps | P1 | Phase 2: Unify critical alerts |
| **§4.4 Smart Calendar** | Multi-event calendar with plan/fact + SLA + export | Calendar module exists partially | Advanced views (week/year) + export missing | P1 | Phase 2: Calendar enhancement |
| **§4.5 Universal Search + Command Bar** | Global search + command palette | Search API exists, UI minimal | Search UI + command bar missing | P1 | Phase 2: Add command palette UI |
| **§5.2 Employee Card** | Unified 360° view (permits, training, medical, SOUT, risks, SIZ, docs) | Card fragmented across modules | Integration/linking missing | P1 | Phase 2: Unify employee card views |
| **§5.3 Site/Object Card** | Unified 360° view (contractors, risks, documents, readiness) | Card exists but incomplete | Risk/readiness aggregation missing | P1 | Phase 2: Site card enhancements |
| **§5.4 Data Quality Layer** | DQ dashboard + completeness scores | Partial validation exists | DQ analytics + recommendations missing | P1 | Phase 2: Add Data Quality module |
| **§6 Documents** | Header/footer engines implemented ✅ | Headers/footers working | Visual diff viewer + advanced compare mode missing | P1 | Phase 1: Document compare UI |
| **§7 LMS** | External integrations (ФРДО, ЕИСОТ, Госключ) | Skeleton present | Integration endpoints not built | P2 | Phase 3: External LMS connectors |
| **§8 Briefings** | Terminal + kiosk mode + screen signature | Not implemented | Field capture UI + offline sync needed | P2 | Phase 3: Field mode (offline-first) |
| **§9 Medical Exams** | Contingent + scheduling + contractor screening | Partial | Scheduling engine + medical document generation | P1 | Phase 2: Medical module completion |
| **§10 SOUT** | Import + link to medical/PPE/risks | Partial | Auto-impact + risk recalculation missing | P1 | Phase 2: SOUT automation |
| **§11 Risk Engine** | Fine-Kinney + hazard library + auto-generation | Working ✅ | Tenant-specific methodologies missing | P1 | Phase 3: Risk methodology flexibility |
| **§12 PPE** | Warehouse + budget + mobile issue | Working ✅ | Budget forecasting + automated orders missing | P2 | Phase 3: PPE forecasting |
| **§13 Incidents** | CAPA + severity matrix + trend analysis | Working ✅ | Trend analysis + predictive flagging missing | P2 | Phase 3: Incident analytics |
| **§14 Inspections** | Mobile + offline + video evidence | Working ✅ | Advanced analytics + repeat-issue tracking missing | P2 | Phase 3: Inspection insights |
| **§15 Contractors** | Guided data collection + readiness engine | Working ✅ | Visitor management + temporary access missing | P2 | Phase 3: Visitor module |
| **§16 Work Permits** | Naray-dopuski + field mobile | Not implemented | Critical enterprise module missing | P2 | Phase 3: Work Permits module |
| **§17 Equipment** | Asset registry + maintenance + criticality | Not implemented | Critical asset module missing | P2 | Phase 3: Equipment module |
| **§18 Committees** | Meeting protocols + voting + task tracking | Skeleton present | Full lifecycle management missing | P1 | Phase 2: Committees completion |
| **§19 НПА & Compliance** | NPA registry + impact analysis + obligation tracking | Partial | Obligation register + compliance tracking missing | P1 | Phase 2: Compliance module |
| **§20 ПБ/ПромБез/Ecology/GO** | Fire/Industrial/Ecology/GO modules | Not implemented | Four vertical modules missing | P2 | Phase 3+: Vertical modules |
| **§21 Terminals & Biometrics** | Kiosk mode + NFC/QR/Face ID + offline | Not implemented | Hardware integration framework missing | P2 | Phase 3+: Terminal framework |
| **§23 CRM** | Leads, deals, billing, partner portal | Minimal | Full sales pipeline + billing missing | P2 | Phase 4: CRM module |
| **§24 Analytics** | Dashboards (1000+) + report builder + scheduled exports | Partial | Report builder + scheduled delivery missing | P2 | Phase 3: Advanced reporting |
| **§25 Workflow & Rules** | Visual workflow editor + rule engine | Not implemented | Critical automation layer missing | P1 | Phase 3: Workflow engine |
| **§26 AI Copilot** | Semantic search + draft generation + explanations | Not implemented | Optional enterprise pack | P3 | Phase 4: AI pack |
| **§27 Mobile Strategy** | PWA + field mode + offline sync + conflict resolution | PWA ready, field mode partial | Field-first UX + robust sync missing | P1 | Phase 2: Mobile-first field mode |
| **§28–31 Backend** | Proper error handling, logging, observability | Implemented ✅ | Advanced observability missing | P1 | Phase 2: Observability hardening |
| **§33 Onboarding** | Wizard + checklist + startup validation | Partial | Guided onboarding flows missing | P1 | Phase 2: Onboarding wizard |
| **§34 Trust & Sellability** | Demo tenant + trial + sandbox + ROI calculator | Demo available | Advanced trial experience missing | P2 | Phase 3: Trial experience |

### Summary of Gaps by Priority

| Priority | Count | Examples | Estimated Phase |
|----------|-------|----------|------------------|
| **P0 (Critical)** | 2 | Final baseline re-run, architectural readiness | Phase 0 (immediate) |
| **P1 (Core vNext)** | 14 | Workspaces, calendar, search, employee/site cards, DQ layer, medical, SOUT, committees, workflow, mobile field mode, onboarding | Phases 1–2 |
| **P2 (Extended)** | 11 | LMS integrations, briefings, terminals, equipment, permits, ПБ/ПромБез/Ecology, CRM, analytics, AI copilot | Phases 3–4 |
| **Not Blocking MVP** | — | Advanced compliance, vertical modules, terminal biometrics | Phase 4+ (future) |

---

## 6. Implementation Phases

### Phase 0 — Release Readiness & Baseline Validation (1–2 weeks)

**Goal:** Ensure MVP is production-ready; execute baseline verification in clean environment; establish release readiness gates.

**Completion Criteria:** TZ-1.1-MVP-01 baseline re-run passes in fresh Codespace/CI.

#### Tasks
| Task | Effort | Owner | Files | Acceptance |
|------|--------|-------|-------|-----------|
| Execute baseline re-verification in clean Codespace | 2h | Next Agent | `docs/audit/BASELINE_VERIFICATION.md` | All tests pass, 1086 backend + 35 frontend green |
| Update baseline results + timestamp | 1h | Next Agent | `docs/audit/BASELINE_VERIFICATION.md` | Results captured with date/environment details |
| Tag RC-001 (release candidate) | 30m | DevOps | `RELEASE_READINESS.md` | RC tag pushed to git, CI passes |
| Document known limitations for v1.0 | 2h | Tech Lead | `KNOWN_LIMITATIONS.md` | Updated with v1.0 scope + v1.1 deferments |

**Critical Blockers:** None remaining (TZ-1.1 infrastructure ready).

---

### Phase 1 — Core UX & Workspace Foundation (4–6 weeks)

**Goal:** Transform platform from module-centric to **task-first, role-based** using workspaces; establish unified card layouts and smart navigation.

**Why Phase 1:** Workspaces and navigation are foundational; vNext spec emphasizes "user sees results, not modules."

#### Domain: Role-Based Workspaces (§4.2)

| Requirement | Current | vNext | Effort | Files |
|-------------|---------|-------|--------|-------|
| 8+ role-specific dashboards | Home screen generic | Safety Specialist, Manager, HR, Compliance, Instructor, Kiosk Operator, Client, Contractor | 4w | Frontend: 8 new page components, 2k LoC |
| KPI cards + quick actions | Dashboard basic | Per-role KPI aggregation, 5–7 actions per role | 3w | Backend: 3 new APIs, 500 LoC; Frontend: 300 LoC |
| Pending tasks inbox | Minimal | Task routing, overdue highlighting, bulk actions | 2w | Backend: 1 new task service, 400 LoC; Frontend: 200 LoC |
| Recent items + saved filters | Not present | Recent 10 items, 3+ saved filters per role | 1w | Backend: 50 LoC; Frontend: 150 LoC |

#### Domain: Document Compare & Diff (§6.8–6.9)

| Requirement | Current | vNext | Effort | Files |
|-------------|---------|-------|--------|-------|
| Visual diff UI (version-to-version) | API exists, no UI | Side-by-side diff viewer with highlights | 2w | Frontend: diff component, 600 LoC |
| Diff content + metadata | Not shown | Show document field changes, attachment diffs | 1w | Backend: 2 APIs, 200 LoC; Frontend: 200 LoC |
| Rollback & restore | Not available | Restore to previous version + approval | 1w | Backend: 1 API, 150 LoC; Frontend: 100 LoC |

#### Domain: Smart Calendar (§4.4)

| Requirement | Current | vNext | Effort | Files |
|-------------|---------|-------|--------|-------|
| Week/Year views | Month only | Add week + year + custom range | 2w | Frontend: 400 LoC |
| Plan/fact visualization | Not shown | Show planned vs. actual events with colors | 1w | Frontend: 200 LoC |
| ICS/Outlook export | Not present | Export to .ics, subscribe to Outlook | 1w | Backend: 1 API, 200 LoC; Frontend: 100 LoC |
| SLA indicators | Not shown | Overdue badge + warning colors per event type | 1w | Frontend: 150 LoC |

#### Domain: Mobile-First Field Mode (§27.1–27.2)

| Requirement | Current | vNext | Effort | Files |
|-------------|---------|-------|--------|-------|
| Offline-first checklist capture | Partial | Full offline queue, auto-resume on reconnect | 3w | Frontend: 500 LoC; Backend: 1 API, 200 LoC |
| Photo + voice notes | Works | Robust media compression, progressive upload | 2w | Backend: media service, 300 LoC |
| QR/barcode scanning UI | Not present | Built-in QR scanner + format validation | 1w | Frontend: 200 LoC |
| Conflict resolution UI | Not present | Show sync conflicts, merge/discard UI | 1w | Frontend: 200 LoC |

**Testing Strategy:**
- Unit tests for workspace KPI aggregation logic
- Integration tests for multi-role access control
- E2E tests for workspaceswitching + data isolation
- Mobile tests for offline capture + sync

**Success Criteria:**
- All 8 workspace variants launch with >90% feature completion
- Document compare UI handles 1000+ document versions without performance degradation
- Calendar exports work with Google Calendar, Outlook, Apple Calendar
- Mobile field mode captures offline and syncs without data loss

---

### Phase 2 — Domain Module Completion & Data Orchestration (6–8 weeks)

**Goal:** Complete partial P1 domains (Medical Exams, SOUT, Committees, Compliance); unify data models across employee + site cards; add data quality layer.

#### Domain: Medical Exams (§9.1–9.3)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Contingent + exam scheduling | Skeleton | Auto-generate from org structure + roles | 3w | Risk engine (identify candidates) |
| Exam results + restrictions | Partial | Link to medical documents, flag restrictions | 2w | Document templates (medical forms) |
| Contractor medical screening | Not present | Pre-assignment validation | 1w | Contractor module |
| Health monitoring hooks | Skeleton | Foundation for future health integrations | 1w | Architecture only (no impl) |

#### Domain: SOUT (§10.1–10.2)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| SOUT import + linking | Partial | Robust import validation + conflict detection | 2w | File upload infrastructure |
| Auto-cascade to PPE/medical | Missing | When SOUT changes, recalculate PPE norms + medical exams | 2w | PPE + medical modules |
| Class of conditions tracking | Basic | Full history + version tracking + diff | 1w | Audit log |

#### Domain: Committees (§18)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Meeting scheduling + roster | Skeleton | Calendar integration, auto-invite, quorum tracking | 2w | Calendar module |
| Protocol + voting | Not present | Digital voting + protocol generation | 2w | Document templates |
| Task assignment from decisions | Not present | Auto-create follow-up tasks from resolutions | 1w | Task module |

#### Domain: НПА & Compliance (§19)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| NPA registry + effective dates | Partial | Full lifecycle, versioning, sunset dates | 2w | Document module |
| Obligation register | Missing | New: bind requirements to roles/processes | 2w | RBAC module |
| Impact analysis | Missing | Show what templates/risks/exams change with NPA update | 2w | Risk + document engines |

#### Domain: Unified Employee Card (§5.2)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| 360° data aggregation | Fragmented | Single source-of-truth view (permits, training, medical, risks, SIZ, docs) | 3w | All domain modules |
| Cross-module events | Missing | Timeline of all events affecting employee | 2w | Event sourcing (P0 done) |
| Readiness/compliance score | Missing | Employee is "ready" for role based on certifications, medical, SIZ, permits | 2w | Compliance calculation engine |

#### Domain: Data Quality Dashboard (§5.4)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Completeness scoring | Not present | Per-entity quality metrics (employee, site, contractor) | 2w | Validation framework |
| Blocking-issue identification | Not present | Flag entities that cannot be used in key workflows | 1w | Validation rules |
| Remediation recommendations | Not present | Suggest fixes for common data gaps | 1w | Rule engine |

**Testing Strategy:**
- Medical: test exam scheduling for 1000+ employee cohorts
- SOUT: test cascade calculations for complex organizations
- Compliance: test obligation satisfaction logic across roles
- Data Quality: validate scoring algorithm on real tenant data

**Success Criteria:**
- Medical scheduling engine handles 50k+ exams/year scheduling in <5 sec
- SOUT changes auto-cascade without manual re-entry
- Employee card loads all 7 data domains in <2 sec
- DQ dashboard flags data issues with >95% precision

---

### Phase 3 — Advanced Features & Vertical Modules (8–10 weeks)

**Goal:** Implement remaining P1 + critical P2 features: workflow engine, advanced analytics, equipment/permits modules, terminal framework.

#### Domain: Workflow Engine & Rules (§25)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Visual workflow editor | Not present | BPMN-inspired, drag-drop, condition builder | 4w | UI framework, process definition schema |
| Rule engine | Not present | If-then rules with priorities, tenant overrides | 3w | Rule definition DSL, executor |
| Execution history + monitoring | Not present | Workflow instance tracking, stuck-job alerts | 2w | Event sourcing, observability |

#### Domain: Equipment & Asset Management (§17)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Asset registry | Skeleton | Full CRUD + maintenance schedule + criticality scoring | 2w | Document module (maintenance docs) |
| Maintenance tracking | Not present | Service schedule, parts, downtime tracking | 2w | Job queue, notifications |
| Equipment-to-risk mapping | Not present | Link assets to risk workflows + CAPA | 1w | Risk + CAPA modules |

#### Domain: Work Permits (§16)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Permit templates + issuance | Not present | Naray-dopuski digital flow + approvals | 3w | Document templates, approval chains |
| Crew manifest + role-based access | Not present | Assign workers to permits + verify permits before work | 2w | RBAC, employee cards |
| Field closure + evidence | Not present | Mobile closure with photo/checklist + archive | 2w | Mobile module, document archive |

#### Domain: Advanced Reporting & Analytics (§24)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Report builder UI | Not present | Template-based, filters, grouping, custom metrics | 3w | Frontend framework, data aggregation |
| Scheduled delivery | Not present | Email/Portal delivery on schedule, format options | 2w | Jobs, notification service |
| Ad-hoc dashboarding | Partial | More pre-built dashboards (incidents, compliance, training ROI) | 2w | Analytics infrastructure |

#### Domain: Vertical Modules (Fire Safety, Industrial, Ecology, GO/ЧС) (§20)

| Requirement | Current | vNext | Effort | Priority | Notes |
|-------------|---------|-------|--------|----------|-------|
| Fire Safety module | Not present | FP objects, extinguishers, drills, inspections | 3w | P2 | Russian GOST compliance |
| Industrial Safety module | Not present | OPO, work permits, inspections, documentation | 3w | P2 | ГОСТ + Rostechnadzor |
| Ecology module | Not present | Emission tracking, waste management, reporting | 2w | P2 | Federal compliance |
| GO/ЧС module | Not present | Civil defense plan, drills, training | 1w | P2 | Focused on drills |

#### Domain: Terminal & Kiosk Framework (§21)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Kiosk UI mode | Not present | Full-screen, simplified navigation, auth by card/biometric | 2w | Frontend framework |
| NFC/RFID integration | Not present | Abstract badge scanner layer, format validation | 1w | Hardware integration |
| Biometric auth hooks | Not present | API contracts for Face ID / fingerprint systems | 1w | Architecture only |

**Testing Strategy:**
- Workflow: test complex BPMN scenarios with 10+ steps, nested conditions
- Equipment: test maintenance schedule recalculation for 5000+ assets
- Permits: test multi-stage approval on mobile with offline capture
- Analytics: test dashboard queries on 10M+ event records <2 sec
- Terminals: test NFC scanning + offline queue in airport/dock scenario

**Success Criteria:**
- Workflow engine executes 1000+ instances/day without bottlenecks
- Equipment module tracks 10k+ assets with maintenance schedules
- Permits flow from request → approval → closure in <1 hour
- Analytics dashboards render in <3 sec for 1-year historical data
- Terminal kiosk works offline for 8 hours, syncs on reconnect without data loss

---

### Phase 4 — Enterprise & Sellability Features (6–8 weeks)

**Goal:** Implement CRM, advanced trial experience, white-label, AI Copilot optional pack, final hardening.

#### Domain: CRM & Billing (§23)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Lead + deal tracking | Not present | Sales pipeline, KP generation, contract tracking | 3w | Document templates, approvals |
| Billing & licensing | Minimal | Seat-based + module-based pricing, usage metering | 3w | Metrics collection |
| Partner portal | Not present | White-label support + reseller controls | 2w | Multi-tenancy |

#### Domain: Advanced Trial & Demo (§34)

| Requirement | Current | vNext | Effort | Dependencies |
|-------------|---------|-------|--------|-------------|
| Demo tenant presets | Partial | Multiple industry presets, guided tours | 2w | Frontend, demo data |
| Trial onboarding | Partial | Step-by-step checklist, in-app help, video tutorials | 2w | Help system, video platform |
| ROI calculator | Not present | Estimate cost savings based on org size | 1w | Analytics |

#### Domain: AI Copilot (§26 — Optional Enterprise Pack)

| Requirement | Current | vNext | Effort | Priority | Notes |
|-------------|---------|-------|--------|----------|-------|
| Semantic search | Not present | Search knowledge base + documents | 3w | P3 | LLM integration optional |
| Draft generation | Not present | Suggest CAPA plans, investigation summaries | 2w | P3 | Human review required |
| Explanations | Not present | Why is employee not ready? What to do? | 2w | P3 | Enterprise feature flag |

#### Domain: Final Hardening (Observability, Performance, Security)

| Requirement | Current | vNext | Effort |
|-------------|---------|-------|--------|
| Observability hardening | Partial | Distributed tracing, SLO dashboards | 2w |
| Performance optimization | Implemented | Index optimization, query caching, pagination | 1w |
| Security penetration test | Not done | Professional audit, fix critical findings | 2w |

**Testing Strategy:**
- CRM: test deal-to-contract workflow with multi-stage approvals
- Trial: test trial tenant isolation + data cleanup after 14 days
- Copilot: test LLM prompt safety + fact-checking
- Performance: run load test 500 concurrent users, 95th percentile <2 sec

**Success Criteria:**
- CRM pipeline tracks 1000+ deals with >90% forecast accuracy
- Trial tenants fully isolated, zero data leakage
- AI Copilot suggestions have >85% user adoption
- System sustains 500 concurrent users at >99% SLA

---

## 7. Prioritized Backlog

### All Items (Sorted by Phase → Priority → Effort)

| Phase | Priority | Task | Area | Modules | Dependency | Est. Effort | Acceptance Criteria |
|-------|----------|------|------|---------|-----------|-------------|-------------------|
| **0** | P0 | Execute baseline re-verification in clean Codespace | Validation | DevOps | None | 2h | All 1086 backend + 35 frontend tests pass |
| **0** | P0 | Tag RC-001 release candidate | Release | DevOps | Baseline green | 30m | RC tag created, CI passes |
| **1** | P1 | Build 8 role-based workspace variants | UX/Navigation | Frontend | RBAC (done) | 4w | All roles have dedicated dashboard with KPI |
| **1** | P1 | Implement KPI aggregation APIs | Backend | Risk/PPE/Training | Domain modules | 3w | 5+ KPIs per role calculated <500ms |
| **1** | P1 | Add document compare/diff UI | UX/Documents | Frontend | Document API (done) | 2w | Side-by-side diff with highlight, version navigation |
| **1** | P1 | Enhance smart calendar (week/year/export) | UX/Calendar | Frontend | Calendar API (done) | 2w | Week + year views, ICS export functional |
| **1** | P1 | Build offline-first field capture | Mobile | Frontend + Backend | Task module, sync engine | 3w | Offline queue survives app restart, syncs on reconnect |
| **2** | P1 | Complete medical exams module | Domain | Backend + Frontend | Risk, RBAC | 5w | Scheduling, restrictions, contractor screening |
| **2** | P1 | Finalize SOUT auto-cascade | Domain | Backend | PPE, Medical | 4w | PPE norms auto-update when SOUT changes |
| **2** | P1 | Build committees module | Domain | Backend + Frontend | Document, Calendar | 4w | Scheduling, voting, protocol, task creation |
| **2** | P1 | Implement НПА & compliance tracking | Domain | Backend + Frontend | Document, RBAC | 4w | NPA registry, obligation register, impact analysis |
| **2** | P1 | Unify employee card (360°) | UX/Dashboards | Frontend + APIs | All domains | 3w | Single card shows permits, training, medical, risks, SIZ, docs |
| **2** | P1 | Add data quality dashboard | Analytics | Backend + Frontend | Validation framework | 3w | DQ scoring, blocking issues, recommendations |
| **2** | P1 | Enhance observability (tracing, SLO) | Infrastructure | Backend | OpenTelemetry (done) | 2w | Distributed traces + SLO dashboards visible |
| **3** | P1 | Build workflow engine (visual editor + rules) | Automation | Backend + Frontend | Event sourcing (done) | 7w | BPMN workflows execute 1000+/day, rule engine handles priorities |
| **3** | P2 | Implement equipment/asset management | Domain | Backend + Frontend | Document, Risk | 4w | Asset registry, maintenance schedules, criticality scoring |
| **3** | P2 | Build work permits (naray-dopuski) | Domain | Backend + Frontend | Approvals, Mobile | 5w | Digital flow, crew manifest, field closure with evidence |
| **3** | P2 | Add advanced analytics & report builder | Analytics | Backend + Frontend | Data aggregation | 5w | Template-based reports, scheduled delivery, 10+ dashboards |
| **3** | P2 | Implement fire/industrial/ecology/GO modules | Vertical | Backend + Frontend | Document, Risk | 9w | 4 modules with compliance forms, tracking, reporting |
| **3** | P2 | Build terminal & kiosk framework | Hardware | Backend + Frontend | Biometric auth stubs | 3w | Kiosk UI, NFC/RFID layer, offline queue |
| **3** | P2 | External LMS integrations (ФРДО, ЕИСОТ) | Integrations | Backend | Training module | 3w | Sync protocols, result imports, certificate validation |
| **4** | P2 | Implement CRM & billing | Domain | Backend + Frontend | Multi-tenancy, Documents | 6w | Lead tracking, deal pipeline, seat-based billing |
| **4** | P2 | Advanced trial & demo experience | Onboarding | Backend + Frontend | Multi-tenancy | 4w | Industry presets, guided tours, ROI calculator |
| **4** | P3 | AI Copilot (semantic search + draft generation) | AI | Backend + Frontend | LLM integration | 5w | Search knowledge base, draft CAPA/summaries, >85% adoption |
| **4** | P3 | White-label & partner portal | Enterprise | Backend + Frontend | Multi-tenancy | 3w | Custom branding, partner dashboard, reseller controls |
| **4** | P3 | Final hardening (perf optimization, security audit) | Quality | DevOps + Backend | All modules | 3w | 500 concurrent users, <2 sec p95, pen-test findings resolved |

---

## 8. Risks & Migration Notes

### Data Migration Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| SOUT import + cascade causes duplicate medical exams | Medium | P1 blocking | Pre-run migration script validates duplicates; dry-run option; transaction rollback |
| Multi-tenant data leakage in compliance/NPA module | Low | Critical | All queries include tenant_id filter; unit tests verify isolation; audit log all compliance actions |
| Employee card 360° aggregation causes N+1 queries | Medium | Performance | Pre-compute readiness score on change; cache aggregation layer; index all joins |
| SOUT version history causes DB bloat | Low | Storage | Partition audit tables by month; archive old records; retention policy (7 years compliance) |

### API Breaking Changes

| Change | Mitigation | Timeline |
|--------|-----------|----------|
| New "workspace" endpoint breaks existing dashboard integrations | Add deprecated-warning header to old endpoint; provide 6-month transition period; client SDK wrapper | 12 months total (6 month notice + 6 month EOL) |
| Medical exam contingent auto-generation changes exam counts | Return old + new counts in response; feature-flag toggle; data reconciliation script | 3 months (preview + gradual rollout) |
| Permit/CAPA/Committee modules add new event types | Extend event enum backward-compatibly (additive only); document new fields as optional | 1 month (field-gating) |

### Architectural Constraints

1. **Feature Flags Required:** All vNext modules ship with `disabled` default; rollout per-tenant
2. **No Stored Procedure Changes:** Backward-compatible database schema only
3. **Event Sourcing Immutability:** Domain events never updated/deleted (only new events added)
4. **Tenant Isolation:** All new tables include `tenant_id`; schema.search_path enforced middleware
5. **Test Coverage:** Each feature ships with >80% unit + integration test coverage

---

## 9. Validation Strategy

### Continuous Validation Gates

#### Per-Phase Gates (Before release to production)
1. **Code quality:** `pylint` pass (backend), `eslint` pass (frontend), no critical security findings
2. **Test coverage:** Minimum 80% coverage on new code paths
3. **Performance:** API p95 ≤ 1s for CRUD ops, <2s for complex aggregations
4. **Regression testing:** All existing P0 tests pass; no feature degradation
5. **Mobile compatibility:** PWA passes Lighthouse audit >85
6. **Data integrity:** Baseline verification passes + fresh environment test

#### Smoke Tests (Daily)
- Login + document creation + approval cycle
- Employee card loads all modules <2s
- Mobile offline capture + sync without data loss
- Search + calendar views responsive
- All dashboards render <3s

#### Load Testing (Weekly)
- 100 concurrent users × 5 min (login + CRUD + search)
- Bulk operations (1000 documents, 500 employee assignments)
- PDF generation pipeline (batch 50 docs)
- Mobile sync (100 devices, offline then reconnect)

#### User Acceptance Testing (Per-phase)
- Phase 1: 5 power users test workspaces, field capture
- Phase 2: 10 domain experts test medical, SOUT, compliance
- Phase 3: 20 ops users test workflow, equipment, permits
- Phase 4: C-level tests CRM, trial experience

---

## 10. Next Agent Task

### Immediate Priorities (Next 1–2 weeks)

**Phase 0 — Release Readiness (CRITICAL PATH):**

Read:
1. `docs/spec/PLATFORM_VNEXT_UPGRADE_SPEC.md` — product vision (scan sections 1–5, 27–36)
2. `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — this document
3. `AI_IMPLEMENTATION_REPORT.md` — current state (focus on "Next Steps")
4. `docs/audit/BASELINE_VERIFICATION.md` — baseline commands

Execute:
1. **Baseline Re-Verification (BLOCKER for RC):**
   - Spin up fresh GitHub Codespaces environment (clean slate)
   - Run: `bash docs/audit/baseline_verification.sh` (or `.ps1` on Windows)
   - Capture actual test counts + timestamps
   - Update `docs/audit/BASELINE_VERIFICATION.md` with fresh results
   - Confirm: 1086+ backend tests pass, 35+ frontend tests pass, login works

2. **RC Readiness Checklist:**
   - [ ] Baseline passes in fresh Codespace
   - [ ] Makefile targets work (cs:reset, cs:dev, cs:test)
   - [ ] README quick-start is accurate
   - [ ] All 18/20 P0 features working (verify via integration tests)
   - [ ] No critical security findings in code review

3. **Tag Release Candidate v1.0-RC1:**
   - After baseline passes, tag commit as `v1.0-RC1`
   - Update `RELEASE_READINESS.md` with RC verdict + date
   - Create GitHub release with RC notes + known limitations

**Do NOT start Phase 1 work until Phase 0 is complete.**

### Phase 1 Preparation (Weeks 3+)

If Phase 0 passes:

1. **Frontend Architecture Review:**
   - Review `frontend/src/pages/` structure for workspace segregation approach
   - Identify which pages can be reused vs. which need workspace wrappers
   - Draft workspace routing strategy (route guards per role)

2. **Backend API Design:**
   - Document 8 new workspace endpoint contracts (GET /api/v1/workspaces/{role}/dashboard)
   - Design KPI aggregation queries (query planner review)
   - Plan Celery background jobs for expensive aggregations

3. **Testing Infrastructure:**
   - Add workspace e2e tests to GitHub Actions
   - Set up performance baselines (API p95 latency)
   - Add mobile browser testing (PWA lighthouse)

### Not to Do (until Phase 1 officially starts)

- Do NOT start building role-based workspaces
- Do NOT modify SOUT/Medical/Compliance modules yet
- Do NOT touch workflow engine or terminal framework
- Do NOT upgrade dependencies without approval

---

## 11. Success Metrics

### By Phase Completion

| Phase | Key Metric | Target | Measurement |
|-------|-----------|--------|-------------|
| **0** | RC Verdict | "READY" | Baseline passes, all P0 tests green |
| **1** | Workspace Adoption | >70% of users via workspace | Telemetry tracking workspace entry points |
| **1** | Mobile Field Capture Success | >95% data survival through offline | A/B test: offline vs online capture |
| **2** | Medical Scheduling | 50k exams/year scheduled in <5s | Load test medical scheduling API |
| **2** | Employee Card Load Time | <2s all modules | Performance monitoring via APM |
| **2** | DQ Score Precision | >95% correctly identify data gaps | DQ module accuracy testing on 1000 employees |
| **3** | Workflow Execution | 1000+ instances/day without failure | Celery task success rate monitoring |
| **3** | Permit Closure Time | <1 hour request → approval → field closure | User journey timing via telemetry |
| **4** | CRM Pipeline | 1000+ deals tracked, >90% forecast accuracy | CRM module adoption + accuracy testing |
| **4** | Trial Conversion | >30% trial → paid (benchmark: 15% SaaS avg) | Trial telemetry + conversion funnel |

---

## 12. Appendix: vNext Specification Cross-Reference

### Mapping vNext Sections to Implementation Phases

| vNext §§ | Title | Phase | Files Affected | Priority |
|----------|-------|-------|-----------------|----------|
| §2 | Product principles | Foundation (all) | All | P0 |
| §3 | Product editions | Phase 4 (trial/editions) | CRM, feature flags | P2 |
| §4.1–4.3 | Navigation + workspaces + command center | Phase 1 | Frontend routing, KPI APIs | P1 |
| §4.4–4.6 | Calendar, search, cards | Phase 1–2 | Calendar, card layouts | P1 |
| §4.7–4.8 | Registries, safe UX | All phases | All modules | P0 |
| §5.1–5.4 | Master data + employee/site cards + DQ | Phase 2 | Employee card, DQ module | P1 |
| §6 | Document factory (mostly done ✅) | Phase 1 (diff UI) | Document compare | P1 |
| §7 | LMS | Phase 3 (external integrations) | Training integrations | P2 |
| §8 | Briefings (kiosk) | Phase 3 | Terminal framework | P2 |
| §9 | Medical exams | Phase 2 | Medical module completion | P1 |
| §10 | SOUT | Phase 2 | SOUT auto-cascade | P1 |
| §11 | Risk engine (mostly done ✅) | Phase 3 (methodology flexibility) | Risk module | P1 |
| §12 | PPE (mostly done ✅) | Phase 3 (forecasting) | PPE module | P2 |
| §13 | Incidents (mostly done ✅) | Phase 3 (analytics) | Incidents module | P2 |
| §14 | Inspections (mostly done ✅) | Phase 3 (insights) | Inspections module | P2 |
| §15 | Contractors (mostly done ✅) | Phase 3 (visitors) | Contractors module | P2 |
| §16 | Work permits | Phase 3 | Permits module | P2 |
| §17 | Equipment | Phase 3 | Equipment module | P2 |
| §18 | Committees | Phase 2 | Committees module | P1 |
| §19 | НПА & compliance | Phase 2 | Compliance module | P1 |
| §20 | Fire/Industrial/Ecology/GO | Phase 3 | Vertical modules | P2 |
| §21 | Terminals & biometrics | Phase 3 | Terminal framework | P2 |
| §22 | Video analytics | Phase 4+ | Optional pack | P3 |
| §23 | CRM | Phase 4 | CRM module | P2 |
| §24 | Analytics & reports | Phase 3 | Report builder, dashboards | P2 |
| §25 | Workflow & rules | Phase 3 | Workflow engine | P1 |
| §26 | AI Copilot | Phase 4 | AI pack (optional) | P3 |
| §27 | Mobile strategy | Phase 1–2 | Field mode, offline sync | P1 |
| §28–31 | Backend architecture | All phases (hardening Phase 4) | All backend modules | P0 |
| §32 | Security | All phases (audit Phase 4) | RBAC, audit log, encryption | P0 |
| §33 | Onboarding | Phase 2 | Onboarding wizard | P1 |
| §34 | Trust & sellability | Phase 4 | Trial, demo, trust center | P2 |
| §35 | Acceptance criteria | All phases | Test suites | P0 |
| §36 | Constraints for AI | All phases (applies to all work) | All modules | P0 |

---

## 13. Document Control

| Field | Value |
|-------|-------|
| **Document ID** | PLATFORM_VNEXT_IMPLEMENTATION_PLAN v1.0 |
| **Created** | 2026-05-02 |
| **Author** | Claude AI (Haiku 4.5) |
| **Status** | Approved for Phase 0 execution |
| **Next Review** | After Phase 0 completion (baseline passes) |
| **Last Updated** | 2026-05-02 |
| **Canonical Location** | `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` |

---

## 14. Summary: Non-Destructive vNext Roadmap

This plan ensures the platform evolves **incrementally and safely**:

1. **Phase 0 (1–2w):** Baseline validation + RC tagging (CRITICAL for release)
2. **Phase 1 (4–6w):** Workspace transformation + document diff + mobile field mode (core UX)
3. **Phase 2 (6–8w):** Domain completion (medical, SOUT, compliance, committees) + data layer (employee card, DQ)
4. **Phase 3 (8–10w):** Advanced features (workflow engine, permits, equipment, analytics, vertical modules)
5. **Phase 4 (6–8w):** Enterprise (CRM, trial, AI Copilot, final hardening)

**Key Principles:**
- ✅ No breaking changes without migration
- ✅ Feature flags for all new capabilities
- ✅ Test coverage >80% on all new code
- ✅ Performance targets met (API p95 ≤ 1s)
- ✅ Tenant isolation maintained throughout
- ✅ Backward compatibility via deprecation periods

**Outcome:** Platform goes from "advanced MVP" → "enterprise-grade SaaS" in 6 months, with zero downtime and zero data loss.

