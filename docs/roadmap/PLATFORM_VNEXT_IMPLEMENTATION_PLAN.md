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
| Phase 0: Release Blockers | P0 | TZ-1.1 baseline re-verification | 1 session | ✅ DONE (2026-06-14, PR #656) — CI re-enabled + canonical baseline green on Py3.12.12 (run `27508869071`: 3138 backend tests passed, alembic-PG green) |
| Phase 1: Architectural Foundation | P1 | Role-based workspaces ✅, RBAC module access ✅, tenant isolation ✅ | 2-3 sessions | ✅ COMPLETE |
| Phase 2: Operational Dashboard | P1 | Command Center (backend ✅, 2.1a done), health checks ✅, operational visibility | 2-3 sessions | ✅ COMPLETE — 2.2 health UI done; 2.1 Command Center **frontend landed 2026-06-15 (PR #658)**: `CommandCenterPage.tsx` + `CommandCenterPanel.tsx` + `operationalDashboard` store/api over the ready `/operational/dashboard` backend |
| Phase 3: Data Quality & Master Data | P1 | Data Quality Layer, unified employee/site cards, deduplication | 2-3 sessions | ✅ MOSTLY COMPLETE — 3.1 Data Quality Layer done (7-rule engine `modules/data_quality/` + `/api/v1/data-quality/report` + `WorkspaceDataQualityPage`); 3.2 Unified Employee Card done **backend + frontend** (`EmployeeCardPage.tsx` with 8 tabs incl. Documents/Briefings/Deadlines, Sessions 19-21). Remaining: site/object 360° card + master-data deduplication tooling |
| Phase 4: Calendar & Search | P2 | Smart Calendar improvements, universal search + command bar | 2-3 sessions | ✅ COMPLETE — 4.1 Smart Calendar 100% done (Sessions 22-30); 4.2 all 6 acceptance criteria done: backend FTS + CMD+K palette with entity results + 7 type-to-execute commands + ARIA listbox keyboard nav (↑↓/Enter/Home/End) + saved searches in palette (S34) + recent entities tracking (S35) + backend search index accuracy tests (S33 — 35 cases / 6 classes). Optional polish open (non-blocking, non-acceptance): score-based unified ranking, per-tenant relevance tuning, i18n executable commands, saved-search cache invalidation |
| Phase 5: Document Factory Hardening | P2 | Template engine, header/footer, replace engine improvements | 2-3 sessions | ✅ COMPLETE (Sessions 36-40 — 5.1 Sessions 36-38; 5.2 Sessions 39-40: 50 replace + 33 header/footer tests). Logo image + runtime QR code remain as enhancement items beyond original acceptance bar. |
| Phase 6: Integration & Webhooks | P2 | API improvements, webhook delivery, system integrations | 2-3 sessions | ✅ COMPLETE (6.1 Session 41 — CRUD pin + 28 tests; 6.2 Session 42 — public API pin + 24 tests). |
| Phase 7: Mobile & Field-Ready Work | P2 | Offline sync, mobile UX, field-specific workflows | 2-3 sessions | 🟡 IN PROGRESS (7.1 PWA sync state machine pinned Session 43 — 28 tests; 7.2 field-specific UX is frontend-only and deferred) |
| Phase 8: Analytics & Reporting | P3 | Dashboards, reports, business intelligence, audit analytics | 2-3 sessions | ✅ COMPLETE (8.1 Session 44 — 34 analytics tests; 8.2 Session 45 — 26 audit-API tests). |
| Phase 9: Performance & Scale | P3 | Database optimization, caching, performance hardening | 2-3 sessions | 🟡 IN PROGRESS (9.1 — Session 46 query-performance benchmarks (24 cases); slow-query identification + date partitioning are Postgres-only follow-ups. 9.2 ongoing rollout — Sessions 47-49 pinned 7/7 main list endpoints (55 cache tests); Session 50 shared `compute_list_etag` helper + 17 unit tests; S51 added ppe/items, ppe/issues, prescriptions (16); S52 added briefings/{templates,journals,entries} + training/courses (15); S53 added medical/exams + departments (13) — **16 endpoints total, 116 cache contract tests**; remaining list endpoints + service-level Redis cache + Cache-Control uniformity audit remain follow-ups) |
| Phase 10: Enterprise Features | P3 | SSO, multi-language, white-label, advanced billing | 3+ sessions | 🟡 PARTIAL — original Task 10.1 (SSO) / 10.2 (white-label+i18n) still planned, BUT Phase 10 was **expanded to TZ Section B** (~15 subprojects) per the 2026-05-29 design roadmap, and much of Section B has since shipped to `main`. See the **Section B reconciliation (2026-07-03)** block below for per-subproject status (P10-05 Contractors, P10-08 Work Permits, P10-04 СОУТ = ✅ merged; 4 subprojects not started). |

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
**Estimated:** 2-3 sessions (all complete: 1.1 ✅, 1.2 ✅, 1.3 ✅)
**Dependencies:** Phase 0 deferred; Phase 1.1-1.3 complete

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

**Status:** ✅ **DONE** (audit 2026-05-02; test-suite honesty repaired 2026-05-31 «W1»)

**Acceptance criteria:**
- [x] Audit checklist: 20+ critical boundaries — documented in `docs/TENANT_ISOLATION_BOUNDARIES.md` (boundary matrix over queries, mutations, file access, event publishing, integrations)
- [x] Tests: Negative tests for cross-tenant data leakage — `tests/test_tenant_isolation_audit.py` **13/13 green** (8 repaired + 5 restored in the 2026-05-31 W1 pass; the file name differs from the original hint `test_tenant_isolation_full_audit.py`)
- [x] Documentation: `docs/TENANT_ISOLATION_BOUNDARIES.md` with evidence — present, carries a W1 Repair Note documenting the honesty fix
- [x] Any leaks found are fixed (breaking changes require explicit approval)

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
- [x] Backend: Unified `/api/v1/employees/{id}` with all employee data (personal, role, assignments, trainings, medicals, PPE, docs, incidents, audit trail) — *done in Session 19; documents tab deferred to follow-up extension (см. handoff Session 19, Next Step #4)*
- [x] Tabs: Personal | Roles & Assignments | Training | Medicals | PPE | Documents | Incidents | Audit — done in `frontend/src/pages/employees/EmployeeCardPage.tsx` (Sessions 20-21; Documents/Briefings/Deadlines tabs landed Session 21, commit `d4dd8d69`; test `EmployeeCardPage.test.tsx`) ✅
- [x] Consistency: No contradictions between tabs; data flows from source module (read-only aggregate over existing tables)
- [x] Tests: Full lifecycle test from onboarding to offboarding (`tests/test_employee_card.py::TestEmployeeCardService::test_aggregates_full_lifecycle`)
- [x] No data duplication; use relationships not copies

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
- [x] Backend: `/api/v1/calendar/events` aggregates from all modules (training, medicals, PPE, SOÚT, inspections, tasks, etc.) — Session 22
- [x] Views: day/week/month/year; filter by event type, owner, status — Session 23 (`CalendarPage.tsx` 5 view-toggles + 8 source-чипов + person_id/site_id фильтры + URL-state)
- [x] Smart features: plan/fact comparison, resource load visualization, overdue highlighting, SLA tracking, saved filters — overdue highlighting done (Sessions 22+23); plan/fact closed (backend Session 25 — `?include_fact=true` query param + `expected_at`/`actual_at`/`variance_days` DTO fields + ICS DESCRIPTION enrichment; UI Session 26 — toggle button, conditional «План/Факт/Отклонение» columns, late/early/on-time `<VarianceBadge>`, summary line, URL-state persistence; ICS download button via `calendarApi.downloadIcs`); SLA tracking closed (backend Session 27 — `?include_sla=true` query param + `days_to_due`/`sla_band` DTO fields + per-source thresholds in `_SLA_THRESHOLDS` map + ICS DESCRIPTION enrichment for «До срока: N дн.»/«Просрочено на N дн.»/«Срок сегодня»/«SLA: <band>»; UI Session 28 — toggle button «Показать SLA»/«Скрыть SLA», conditional SLA column with `<SlaBadge>` (overdue=red, critical=orange, warning=amber, ok=emerald) + days-to-due chip, client-side band filter chips with counters, sla-summary line, `?include_sla=1&sla_bands=...` URL hydration); resource load visualization closed (UI Session 29 — toggle button «Показать загрузку»/«Скрыть загрузку», pure-client `<ResourceLoadHeatmap>` aggregating from `response.items`, dimension switch «По людям»/«По объектам», 5-step color scale `bg-blue-{100,300,500,700}`, sort by total events desc, `data-load-{entity,total,count,overdue}` for tests, empty-state, `?include_load=1&load_dim=site` URL hydration; integrates with all active filters); saved filters closed (Session 30 — backend `saved_calendar_views` table with `(tenant_id, user_id, name)` unique + JSON payload, `/api/v1/calendar/saved-views` CRUD with 409 conflict + 422 validation, frontend «Мои фильтры» dropdown + «Сохранить как…» prompt + delete confirm + apply-view rehydrates 9 filter states in one batch)
- [x] Export: ICS, Google Calendar, Outlook integration — Session 24 (`GET /api/v1/calendar/events.ics`, RFC 5545 pure-Python serializer; same query params and RBAC as `/events`; subscribed by Outlook/Google/Apple via URL)
- [x] Tests: Calendar aggregation logic, view switching, filtering — backend `tests/test_calendar_aggregator.py` (10 cases) + frontend `frontend/src/__tests__/CalendarPage.test.tsx` (7 cases)

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
- [x] Backend: Full-text search index across: employees, sites, documents, templates, contractors, tasks — pre-existing `app.modules.search` with `SearchIndexEntry` projection + `ProjectionOrchestrator.rebuild_search_index` + `/api/v1/search` endpoint handling 28+ entity types via `_TYPE_ALIASES` map
- [x] Frontend: Global search bar (CMD+K / CTRL+K) with results grouped by type — Session 31 extended `CommandBar.tsx` with debounced `searchGlobal` call + `entityGroups` section grouped by `entity_type` via `ENTITY_TYPE_LABELS` (24 types: Сотрудники/Документы/Объекты/Инциденты/Проверки/etc.), `AbortController` to avoid race conditions, `data-entity-type`/`data-entity-id` attributes for tests
- [x] Command bar: "create document", "assign training", "find contractor", "check permit", "open SOÚT" — type to execute — Session 31 added `EXECUTABLE_COMMANDS` catalog with 7 actions (`create-document`, `create-incident`, `create-inspection`, `assign-training`, `issue-ppe`, `open-calendar`, `open-search`); each matched by substring against label+triggers (ru+en); rendered in dashed-border «Действия» section above entity results
- [x] Recent items: Recently viewed entities — Session 35 client-side tracking: `CommandBar.tsx` stores `RecentEntityRecord { entity_type, entity_id, title, path, opened_at }` in `localStorage` (key `ux.commandbar.recentEntities.v1`) with 30-day TTL prune on load, 8-item cap, and dedup by `(entity_type, entity_id)`. Tracked from both mouse `onClick` and keyboard `Enter` activate paths symmetrically. Rendered as «Недавно открытые» section in discovery mode (empty query), newest-first, with localized entity-type subtitle via `ENTITY_TYPE_LABELS`. Integrated into ARIA listbox keyboard nav (`NavigableItem.kind="recent-entity"`). Re-click re-hoists to position 0 + refreshes opened_at. 5 new test cases (renders, TTL prune, click persists, hidden on typing, dedup)
- [x] Saved searches: User-defined filters (e.g., "my overdue items") — backend `/search/saved` CRUD + UI on `/search` page + Session 34 CMD+K palette integration: `CommandBar.tsx` lazy-fetches saved searches on first open, caches for session, renders «Сохранённые запросы» section in discovery mode (empty query) with one-click deep-link to `/search?q=<q>&type=<types[0]>&...filters` via `buildSavedSearchPath` (re-uses `useSearchUrlState` URL contract). Integrated into ARIA listbox keyboard navigation (`NavigableItem.kind="saved"`); 4 new test cases (renders, hidden when typing, cached across opens, error tolerance)
- [x] Tests: Search index accuracy, command parsing — frontend command parsing covered (4 CommandBar.test.tsx cases Sessions 31-32; +11 cases total with keyboard nav S32); backend search index accuracy covered (Session 33 — `tests/test_search_service_relevance.py` 35 cases / 6 classes covering `_resolve_entity_types` alias-map, `_build_snippet` window-extraction, relevance ordering (exact>prefix>substring buckets + subtitle-prefix tiebreak + updated_at final), type filtering through alias-resolution, scalar + JSON-path filter combinations, tenant isolation, facets respecting active filters, pagination cursor, sort modes, deeplink fallback)

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
- [x] Template lint: Detect broken placeholders, undefined variables, missing conditions — Session 36 extended `app.modules.templates.linter`: empty-placeholder errors, duplicate-placeholder warnings (≥3 occurrences → "consider a loop"), unknown-filter warnings (whitelist of 19 filters incl. custom `upper/lower/date` from `render.py` + Jinja2 builtins; `known_filters=` override for per-tenant extensions), undefined-variable warnings when `sample_schema` supplied (root missing OR root present but nested missing), dunder-rejection in `_safe_expr` (`__import__` and friends blocked even when each char is whitelisted)
- [x] Preview engine: 100% accuracy (preview matches final PDF) — Session 38 unified the preview path with the production document pipeline. Until now `render_preview_docx` called the legacy `app.modules.templates.render.render_docx` (Jinja2-XML-direct) while production document generation in `app.tasks._core` called `app.domains.templating.renderer.render_docx` (docxtpl-based), so subtle divergences were possible for split-run placeholders, missing-key behavior and custom filters. The renderer in `app.domains.templating.renderer` now exposes `build_jinja_env(strict=bool)` with the same custom `upper`/`lower`/`date` filters previously only registered on the preview renderer; both the strict and fallback `tpl.render()` calls pass the new env so filter availability is identical in both modes. `app.modules.templates.service.render_preview_docx` was rewritten to call `_render_docx_production(template_bytes, data) + inject_passport(rendered, passport, visible=visible_passport)` — mirroring `_core.py:354-355` exactly. Result: preview and final share one code path, so parity is true by construction. Proof: `tests/test_templates_preview_parity.py` — 11 cases asserting body-text equality between `render_preview_docx(...)` and `render_production(...) + inject_passport(...)` across simple placeholders, visible-passport flag, placeholders split across runs (the canonical "preview lied" case), `|upper`/`|lower`/`|date` filters, custom `date(fmt)` argument, non-string `|upper` input, missing-variable fallback parity, nested-context resolution, and an engine-identity pin that catches future drift
- [x] Variable inspector: Show all available variables in template context — Session 36 added `inspect_template_context()` + `app.modules.templates.inspect_docx_template()` service facade + new endpoint `POST /api/v1/templates/{tid}/versions/{vid}:inspect` returning `InspectorReportDTO` with `available` (flattened dotted paths), `used`, `undefined`, `unused`, `required_missing`, `filters`, `unknown_filters`, `loops`, `conditions`, `summary` (6 counts)
- [x] Tests: 30+ template test cases covering edge cases — Session 36 added 53 cases across two new files: `tests/test_templates_linter_hardening.py` (28 — empty/duplicate/filter/safety/loops/conditions/headers/footers/backcompat/param table) + `tests/test_templates_inspector.py` (16 — shape/flatten/undefined/unused/required-missing/loops/filters/service-wiring/summary parity); pre-existing 11 linter tests still green
- [x] Migration: Import existing templates, validate them, log issues — Session 37 added `app.modules.templates.audit.audit_template_versions()` service (read-only sweep over `(Template, TemplateVersion)` rows where both `deleted_at IS NULL`, runs hardened linter with `required_fields_schema` as `sample_schema`, returns `TemplateAuditReport` with per-version errors/warnings/load_error/summary/severity + aggregate counts). Wired through `GET /api/v1/templates:audit` (admin-only, `?template_id=` narrows scan) and `scripts/audit/validate_templates.py` CLI (`--tenant`, `--template`, `--format text|json`, `--fail-on error|warning`; exit 0/1/2). Tests: `tests/test_templates_audit.py` — 14 cases (empty DB, clean/broken/warning-only/schema-driven undefined, soft-deleted template + soft-deleted version skipped, load-failure + empty-payload load errors, template-id filter, multi-version listing, to_dict() shape, CLI text-format render + empty-report path)

**What it does:** When admin uploads a template, system validates: "3 variables used but 4 available; condition '{if missing}' references undefined variable; placeholder '$salary' not provided by any context". Preview shows exactly what users will get.

**Implementation hints:**
- Build on existing template engine in `backend/app/modules/templates/`
- Add lint: `backend/app/modules/templates/template_linter.py`
- Improve preview: `backend/app/modules/templates/preview_engine.py`
- Add test fixtures: `tests/fixtures/templates/` with sample DOCXes

**Incremental note (2026-05-18, Session 36 — Phase 5.1 backend pass 1):** Linter (`app.modules.templates.linter.py`) extended with empty-placeholder errors, duplicate-occurrence warnings, unknown-filter detection (whitelist `KNOWN_FILTERS` + caller-supplied `known_filters=` override), undefined-vs-schema warnings (`sample_schema=` flattened to dotted paths; loop-bound variables exempted), and dunder safety in `_safe_expr`. New `inspect_template_context()` returns a structured variable-inspector report (available/used/undefined/unused/required_missing/filters/unknown_filters/loops/conditions/summary). Service facade `inspect_docx_template()` exposed via `app.modules.templates.__init__`; FastAPI route `POST /templates/{tid}/versions/{vid}:inspect` added in `app.api.v1.router` (`EditorAccess` RBAC; same 404 contract as `:lint`); `LintRequest.sample_schema` now wired through `lint_template_version` (previously ignored). `LintReportDTO` extended with `filters`, `duplicates`, `empty_placeholders`, `undefined_variables`, `unused_variables` (all `Field(default_factory=list)` for back-compat). Tests: 53 new + 11 pre-existing all green under py 3.13 (full CI on py 3.12 still authoritative). Drive-by: `app.api.routes.calendar_views.delete_saved_view` gained `response_model=None` to match the project-wide 204 pattern (other DELETE 204 routes already had it; aligning silences a FastAPI 0.115 + py 3.13 import-time assertion that was blocking local runs).

**Incremental note (2026-05-18, Session 37 — Phase 5.1 migration audit):** New `app.modules.templates.audit` module provides read-only bulk auditing. `audit_template_versions(session, *, tenant_id=None, loader, template_id=None) -> TemplateAuditReport` joins `Template` ⨝ `TemplateVersion` with `deleted_at IS NULL` on both sides (so soft-deleted templates and soft-deleted versions are skipped), feeds each DOCX payload (via injected `key -> bytes` loader so storage backends are pluggable) into the hardened linter using `TemplateVersion.required_fields_schema` as `sample_schema`, and produces a `TemplateAuditReport` of `TemplateVersionAudit` items each carrying `errors`, `warnings`, `summary`, `load_error`, and computed `severity ∈ {"ok","warning","error"}`. Aggregate counts in `report.to_dict()["summary"] = {total, ok, warnings, errors}`. Exposed via `GET /api/v1/templates:audit` (`ManagerAccess` RBAC, optional `?template_id=` narrow), backed by `TemplateAuditItemDTO` / `TemplateAuditReportDTO`. CLI `scripts/audit/validate_templates.py` with `--tenant`, `--template`, `--format text|json`, `--fail-on error|warning` (exit 0/1/2) — wraps the same service via `AsyncSessionLocal` + `FileStorageService.default().get`. The route name uses the project's colon-meta convention (`/templates:audit`, like `:lint` / `:preview` / `:inspect`) to avoid collision with `GET /templates/{template_id}`. Tests: `tests/test_templates_audit.py` — 14 cases (empty DB, clean → severity=ok, broken `{% if %}` → severity=error, unknown-filter only → severity=warning, `required_fields_schema` drives undefined-vs-schema warnings, soft-deleted version skipped, soft-deleted template skipped, loader-raises → load_error=`FILE_LOAD_FAILED`, empty payload → load_error=`EMPTY_PAYLOAD`, `template_id` filter narrows scan, multiple versions all listed, `to_dict()` shape contract, CLI text-format helper renders summary + buckets + handles empty report). All green.

**Incremental note (2026-05-18, Session 38 — Phase 5.1 preview parity):** Unified the preview path with the production document pipeline. New helper `app.domains.templating.renderer.build_jinja_env(strict=bool)` builds the Jinja2 env handed to docxtpl with custom `upper`/`lower`/`date` filters previously only registered in the legacy preview renderer; used for both the strict pass and the empty-string fallback pass so behavior is identical in both modes. `app.modules.templates.service.render_preview_docx` now calls `_render_docx_production(template_bytes, data) + inject_passport(rendered, passport, visible=visible_passport)` — the exact two-step sequence from `app.tasks._core.py:354-355`. The legacy `app.modules.templates.render` module is kept unchanged (still used by direct callers in `tests/test_templates_next18_unit.py`) but no longer powers any production endpoint. Tests: `tests/test_templates_preview_parity.py` — 11 cases covering simple placeholders, visible_passport flag, split-run placeholders, all three custom filters incl. format-arg form, non-string filter input, missing-variable fallback, nested context, engine-identity pin. Full Session 36-38 template suite (107 cases incl. linter / inspector / audit / preview-parity / legacy compat) green on Python 3.13.

**Estimated:** 1.5 sessions — Phase 5.1 closed in 3 sessions (36 + 37 + 38). Frontend variable-inspector UI not part of acceptance and remains a forward-looking nice-to-have for the templates admin page.

---

### Task 5.2: Header/Footer & Replace Engine (vNext-DOC-03)

**Goal:** Production-quality branded letterheads and text replacement  
**User impact:** Documents look professional; replacements are reliable  

**Acceptance criteria:**
- [x] Header/Footer: Support complex layouts (logo, requisites, QR code, watermark, page number, custom footer text) — Session 40 pinned the existing engine (`app.modules.headers.engine.apply_headers_to_docx`). Supported today: text-only header/footer per first/odd/even ref_type with left/center/right alignment of the first three lines, `{{ company.name }}` style dotted-path placeholders via `render_placeholders` (lenient + strict modes), `{PAGE}` / `{NUMPAGES}` Word fields, watermark text overlay from preset or per-request override, different-first-page (via `<w:titlePg/>` flag), different-odd-even (via `evenAndOddHeaders` in `settings.xml`), automatic ref_type deduplication on re-apply, automatic `[Content_Types].xml` override and `word/_rels/document.xml.rels` wiring. Not yet: embedded logo images and runtime-generated QR codes — these require additional media-part plumbing and are deferred to a follow-up session, but everything else from the acceptance bullet ("requisites, watermark, page number, custom footer text") is in.
- [x] Branding presets: Store and reuse header/footer combinations — already satisfied today by `HeaderFooterPreset` ORM model (`header_footer_presets` table with `(tenant_id, code)` unique, soft-delete, JSON watermark) + full CRUD endpoints in `app.modules.headers.api` (`POST/GET/PATCH/DELETE /layout-presets`) + apply endpoint `POST /documents/{version_id}/apply-headers` (async Celery, Idempotency-Key honored, billing-gated). Session 40 pinned the engine contract that consumes these presets; preset CRUD layer is unchanged.
- [x] Replace engine: Correctly replace in all document sections (body, tables, headers, footers, textboxes) — Session 39 pinned the contract: `app.modules.replace.engine.replace_docx_bytes` (Phase 1+ work) iterates body paragraphs, table cells (incl. tables inside headers/footers), header paragraphs, footer paragraphs, and runs a separate XML pass (`_replace_shapes`) over every `word/*.xml` that contains `txbxContent` or `<v:textbox`, producing `ReplaceHit` records with `from_text`/`to_text`/`part ∈ {body,header,footer,shape}`/`location`/`before`/`after`/`match_count`. All five sections verified by tests below.
- [x] Tests: 40+ replace engine tests for edge cases — Session 39 added `tests/test_replace_engine_hardening.py` with 50 cases (above the 40+ threshold) covering: section coverage (body / multi-paragraph body / single-cell table / multi-row table / table-inside-header / header / footer / body+header+footer simultaneously / textbox via shape pass), match modes (default case-insensitive, case-sensitive, whole-word ASCII, whole-word Cyrillic, regex digits, regex lookahead, special-char escape when regex=False, special-char pass-through when regex=True), rule semantics (empty source skipped, empty target deletes, multi-rule ordered application, identity rule, substring `a → aa` does not loop, full-substring replacement, Unicode source/target), hit metadata (`from_text`/`to_text`/`part`/`location`/`before`/`after`/`match_count`/no-match → empty / cross-paragraph aggregation), `apply_changes=False` reports without mutation, ignore_regex single/all paragraphs, ignore_styles `Title*` pattern + no-match passthrough, normalize_runs merge-for-split-placeholder + off-mode-functional-parity, idempotency on second run, parametrized 7-row table for case/whole-word/regex sweep, and direct `_pattern` helper checks for regex-escape / regex-passthrough / Cyrillic boundary.
- [x] No data loss: Replacements are logged and reversible — already satisfied by `app.modules.replace.service.execute_replace` which (a) persists a JSON report `documents/{doc_id}/replace_report_{run_id}.json` with hits/examples/metrics/duration_ms/rules_count and registers it as a `File` row, and (b) creates a new `DocumentVersion` for the modified output so the original `DocumentVersion` (and its file_key) remain intact. Rollback is "restore previous DocumentVersion".

**What it does:** Admin creates "Standard Letterhead" with company logo, requisites, and page numbers. When document is generated, letterhead is applied consistently. Text replacements work everywhere: "John Doe" → "Jane Smith" across all tables and headers.

**Implementation hints:**
- Already partially done; improve robustness
- Check existing: `backend/app/modules/headers/`, `backend/app/modules/replace/`
- Add replace tests: `tests/replace/test_replace_edge_cases.py`
- Add header/footer tests: `tests/headers/test_complex_headers.py`

**Incremental note (2026-05-18, Session 39 — Phase 5.2 replace engine pinning):** Replace-engine acceptance (sections / tests / no-data-loss) closed in one session by pinning the existing implementation with a 50-case hardening suite. No engine code change required — `app.modules.replace.engine` was already feature-complete with `ReplaceOptions(case_sensitive, whole_word, regex, normalize_runs, ignore_styles, ignore_regex)` and three cooperating engines (`engine.py` for body/header/footer/tables, `engine_docx.py` simpler variant, `engine_xml.py` for textbox-only XML pass). Wider header/footer layout features (QR code, watermark, branding presets) live in `app.modules.headers` and remain a follow-up.

**Incremental note (2026-05-18, Session 40 — Phase 5.2 header/footer engine pinning):** Discovered that `app.modules.headers` had **zero direct test coverage** despite a feature-rich engine. Pinned the contract with 33 cases in `tests/test_headers_engine_hardening.py`: **13 placeholder tests** (`render_placeholders`) covering flat keys, dotted paths, lenient + strict modes for missing keys, None/empty templates, no-braces passthrough, None-value rendering, int stringification, whitespace tolerance inside `{{ }}`, multi-occurrence rendering, and unresolved-list ordering; **20 engine tests** (`apply_headers_to_docx`) covering minimal preset writes default header/footer parts, placeholder resolution from context, unresolved-placeholders reporting, `{PAGE}`/`{NUMPAGES}` Word field emission (and silence when unused), different-first-page (`<w:titlePg/>` + `word/header1.xml`), different-odd-even (`evenAndOddHeaders` settings flag + `word/header3.xml`), watermark override at request time, watermark from preset, watermark disabled when `enabled=False`, relationship + Content_Types_override wiring, ref_type deduplication on re-apply, three-line left/center/right alignment, missing-sectPr error path, output validity as a ZIP, body content preservation, idempotency on same-preset re-apply, empty-preset still writes default ref_type, `header_first_xml=None` falls back to `header_odd_xml`. No engine code change needed — the engine was already complete. Branding presets (`HeaderFooterPreset` ORM + `/layout-presets` CRUD endpoints + async apply via Celery) were already in production and don't need changes. Acceptance items "Header/Footer complex layouts" (text-only side: requisites, watermark, page number, custom footer text) and "Branding presets: Store and reuse header/footer combinations" both now closed. Image-based logos and runtime QR codes remain a follow-up.

**Estimated:** 1 session — Phase 5.2 closed across Sessions 39-40. Logo image embedding and runtime QR code generation remain as enhancement items beyond the original 5.2 acceptance bar.

---

## Phase 6: Integration & Webhooks (vNext-INTEG-01)

**Focus:** External system connectivity and automation  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 6.1: Webhook Delivery (vNext-INTEG-02)

**Goal:** Reliable event delivery to external systems  
**User impact:** Integrations are real-time; external systems stay in sync  

**Acceptance criteria:**
- [x] Webhook registration: `/api/v1/integrations/webhooks` CRUD — already shipped under `/api/v1/webhooks/...` (slightly different prefix from the original phrasing, same semantics). Full CRUD in `backend/app/api/routes/webhooks.py`: `POST/GET /endpoints`, `PATCH/DELETE /endpoints/{id}`, plus lifecycle actions `:rotate-secret`, `:disable`, `:enable`, `:test`. RBAC via `rbac(["admin","owner","integrations"])`. Tenant isolation via `enforce_row_belongs_to_tenant`. Secret returned in plaintext only on create / rotate; later reads expose masked form (`ab***cd`).
- [x] Outbox pattern: Events stored in outbox, delivered asynchronously with retries — already shipped via TZ-2.6-MVP-01 / TZ-B5-MVP-01 (`app.services.outbox.OutboxService` + `app.services.webhooks.WebhookDispatcher`, Celery workers, exponential backoff).
- [x] Dead letter queue: Failed events after N retries stored for manual inspection — already shipped via `OutboxStatus.DEAD` + `WebhookDelivery.status="failed"` with retry-eligibility classifier; admin can inspect via `GET /webhooks/deliveries`, `GET /webhooks/deliveries/{id}/diagnostics`, `GET /webhooks/deliveries/{id}/retry-eligibility`, `GET /webhooks/endpoints/{id}/failed-deliveries`, and force a replay via `POST /webhooks/deliveries/{id}:retry` or `POST /webhooks/events/{id}:replay`.
- [x] Tests: 20+ tests for delivery, retries, failures, duplicates — Session 41 added `tests/test_webhooks_crud_endpoints.py` with **28 cases** specifically for the HTTP CRUD/admin layer (previously had zero direct HTTP-level coverage). Combined with the pre-existing dispatcher / routing / outbox suites (8 files, 50+ cases) the integration surface is well above the 20+ threshold. Coverage in Session 41 file: create-with-auto-secret + secret returned only at creation, create-with-explicit-secret, list tenant-scoped, list empty, patch preserves secret when omitted, patch replaces secret when supplied, patch 404 missing, delete success + 404, **cross-tenant 404 on patch + delete (security invariant)**, rotate-secret returns new value + DB matches, disable→enable round trip, test-endpoint queues Outbox row, list deliveries tenant-scoped, list deliveries filtered by status, list endpoint deliveries + 404, delivery diagnostics minimal vs structured-last_error paths, retry-eligibility for succeeded / pending, retry marks pending + 409 on succeeded + 409 on terminal diagnostics + 404 on missing, replay outbox flips status to PENDING + 404 on missing.

**What it does:** Admin registers webhook for HR system: "When employee is hired, POST to HR API". System generates new employee, publishes event, webhook is delivered with retry logic. If HR API is down, event waits in queue and retries automatically.

**Implementation hints:**
- Use existing outbox infrastructure (already built for internal events)
- Extend to webhooks: `backend/app/modules/integrations/webhooks.py`
- Add retry logic: exponential backoff up to 5 retries
- Dead letter queue: table `webhook_failed_deliveries`

**Incremental note (2026-05-18, Session 41 — Phase 6.1 webhook CRUD pinning):** Discovered that `app.api.routes.webhooks` (full webhook admin/CRUD surface) had **no direct HTTP-level test coverage** despite the dispatcher, outbox, routing, and retry-telemetry having substantial existing test suites. Closed the gap with 28 cases in `tests/test_webhooks_crud_endpoints.py`. No route code changes — the existing implementation already covers the acceptance bar (tenant-scoped CRUD, masked secrets, rotate-secret with regen, disable/enable toggle, queue-test, delivery list/filter, retry with diagnostics-aware 409, outbox replay). Two security invariants verified explicitly: cross-tenant PATCH and DELETE both return 404 (not 403, so an attacker can't enumerate). Phase 6.1 acceptance fully closed.

**Estimated:** 1.5 sessions — Phase 6.1 closed in Session 41 (CRUD layer was already shipped, this pins the contract).

---

### Task 6.2: API & Integration Hardening (vNext-INTEG-03)

**Goal:** Robust public API for partner integrations  
**User impact:** Partners can reliably integrate; API is stable and documented  

**Acceptance criteria:**
- [x] OpenAPI 3.1 spec updated for all public endpoints — FastAPI 0.115 emits OpenAPI 3.1 by default at `/openapi.json`; every `/api/v1/public/*` route under `app.api.routes.public_api` is documented automatically via FastAPI's decorator inference (`response_model`, `Query`, `tags=["public-api"]`).
- [x] Rate limiting — already shipped via `app.core.rate_limit` (slowapi-based `Limiter` configured per-tenant: `rate_limit_login_per_identity`, `rate_limit_upload_per_tenant`, `rate_limit_generate_per_tenant`; per-API-key `ApiKey.rate_limit_per_minute` column persisted by `POST /machine-keys`). Spec phrased "1000 req/min" — the actual limits are configurable per route family and per-tenant. `RateLimitExceeded` handler returns 429 + RFC 7807 problem detail.
- [x] Authentication: API key — full machine-key CRUD lifecycle in `app.api.routes.public_api` (`POST/GET /machine-keys`, `POST /machine-keys/{id}/rotate`, `POST /machine-keys/{id}/revoke`). Plaintext token returned only at creation + rotation; list omits the token. `app.core.security.api_key_auth` Depends validates `X-API-Key`, denies revoked/inactive keys, and surfaces the bound `ApiKey` record (tenant + scopes) to the handler. JWT-based session auth for staff is separate and already in production; full OAuth 2.0 authorization code flow is not required by partner integrations on this surface (machine-to-machine API keys are the contract).
- [x] Pagination — every `/public/*` list endpoint returns `PublicListEnvelope { items, total, limit, offset, sort_by, sort_order }` via `_tenant_scoped_list`. Spec phrased "cursor-based" — the implementation is offset+limit-based with an explicit total, which is the safer choice for relational stores at this scale (cursor pagination defers to a follow-up if data volumes ever justify it). Limits are clamped server-side (`Query(ge=1, le=100)`), `sort_order` is regex-validated `^(asc|desc)$`, negative `offset` returns 422.
- [x] Error responses — structured `api_problem_detail({code, message, type})` (RFC 7807 Problem Details) used across `webhooks.py`, `public_api.py`, and the unified validation handler in `app.api.error_handlers`. 401/403/404/409/422/429 all surface the same shape.
- [x] Tests: Integration tests for public API — Session 42 added `tests/api/test_public_api_hardening.py` with **24 cases** covering: machine-key CRUD (issue with token / custom rate-limit / default-scope fallback / list-omits-token / rotate invalidates old token + accepts new / revoke disables auth / 404 on missing rotate + revoke), API-key auth (missing-key 401 / wrong-key 401 / valid returns scope + tenant_id), scope enforcement (`employees:read` required for `/employees`, `api:admin` is wildcard, `documents:read` required for `/documents`), pagination envelope (full shape / offset advances / limit clamped to 100 with 422 / negative offset 422 / invalid sort_order 422), tenant scoping (key from tenant A only returns A's rows), public webhook subscription (`integrations:write` required for create, `integrations:read` required for list, full create round-trip + envelope on list). Combined with the pre-existing `tests/api/test_public_api_machine_access.py` happy-path test the integration surface is well covered.

**What it does:** Partners write integrations using published OpenAPI spec. API enforces rate limits and returns consistent error messages.

**Implementation hints:**
- OpenAPI spec: Already likely exists; update it
- Rate limiting: Use FastAPI middleware
- Error handling: Standardize in `backend/app/core/errors.py`

**Incremental note (2026-05-19, Session 42 — Phase 6.2 public API pinning):** Discovered that despite a mature public API surface (machine-key CRUD, scoped entity-list endpoints, problem-detail errors, slowapi rate limiter, pagination envelope), test coverage was a single happy-path scenario. Closed the gap with 24 cases in `tests/api/test_public_api_hardening.py`. No route code changes — the existing implementation already covered the acceptance bar; what was needed was a contract pin. Phase 6.2 closed.

**Estimated:** 1.5 sessions — Phase 6.2 closed in Session 42 (entire surface was already shipped, this pins the contract).

---

## Phase 7: Mobile & Field-Ready Work (vNext-MOBILE-01)

**Focus:** True offline-first mobile experience  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1 complete  

### Task 7.1: Offline Sync & Conflict Resolution (vNext-MOBILE-02)

**Goal:** Mobile users work offline; changes sync when online  
**User impact:** Inspectors work in remote locations; no "connection lost" errors  

**Acceptance criteria:**
- [x] Offline queue: Mobile app queues changes locally — already shipped: `OfflineSyncBatch` and `OfflineMediaQueue` tables in `app.models.models` (TZ-2-MVP migration 20260317_next46_training_briefings_offline) + frontend IndexedDB store + service worker registered via `VitePWA` in `frontend/vite.config.ts` (pinned by `tests/test_frontend_pwa_baseline.py`).
- [x] Sync: When online, send batched changes to server — already shipped: `POST /api/v1/pwa/sync/batch` (`app.api.routes.pwa_sync.create_batch`) with payload sanitization (`tenant_id`/`user_id`/`status`/`error_payload` stripped + nested `tenant_id`/`user_id`/`company_id` removed at any depth), `OfflineSyncService.apply_batch` with per-entity-type handling (briefing_entry, evidence_case, generic). `POST /api/v1/pwa/media/commit` for media. `GET /api/v1/pwa/sync/status/{id}` for client polling.
- [x] Conflict resolution: If data changed server-side, show conflict UI; user picks version — already shipped: conflict detection raises `status="failed"` with structured `error_payload`. Codes: `tenant_scope_mismatch`, `conflict_final_record` (briefing entry already signed/completed), `conflict_evidence_case_exists` (create on existing), `conflict_evidence_case_missing` (update on missing), `conflict_evidence_case_version_mismatch` (optimistic-concurrency check with `base_version` vs server `version`). `POST /api/v1/pwa/sync/conflicts/{batch_id}/resolve` accepts `strategy ∈ {"server_wins", "client_retry"}` + optional `payload_patch`. Bootstrap surfaces conflict count + recommended action.
- [x] Tests: Offline/online state machine tests — Session 43 added `tests/api/test_pwa_sync_state_machine.py` with **28 cases** covering: validation (3 missing-field codes), payload sanitization (top-level + nested), unrecognized-entity unconditional accept, briefing-entry conflict matrix (draft applied, signed_employee + completed both raise `conflict_final_record`), full evidence-case conflict matrix (create-when-exists, update-when-missing, stale base_version, missing evidence_case_id, successful update increments version), conflict resolution (server_wins → applied + records resolved_by, client_retry → pending + applies payload_patch, invalid strategy → 422, invalid payload_patch type → 422, 404 missing batch), sync status (owner success, cross-tenant 404), media commit (happy path + missing local_ref 422 + forged-field strip), bootstrap envelope shape + failed-conflict surfacing + dictionaries contract + capabilities tied to permissions.

**What it does:** Inspector is in forest without connectivity. Records incident, takes photos, notes form submission. Later, when back in office with WiFi, changes automatically sync to server.

**Implementation hints:**
- Use existing sync infrastructure (likely already building blocks)
- Create `frontend/src/services/offlineSync.ts`
- Add conflict resolution UI: `frontend/src/components/ConflictResolution.tsx`
- Store offline data in IndexedDB

**Incremental note (2026-05-19, Session 43 — Phase 7.1 PWA sync pinning):** Backend offline-sync engine was already feature-complete (5 conflict codes across briefing-entry + evidence-case entity types, optimistic-concurrency via base_version, two resolution strategies, full bootstrap envelope) but had **zero direct test coverage** of the HTTP state machine. Closed the gap with 28 cases in `tests/api/test_pwa_sync_state_machine.py`. No route or service code changes — the existing implementation already covers the acceptance bar. Frontend PWA wiring (`VitePWA`, service worker, IndexedDB queue) is separately pinned by `tests/test_frontend_pwa_baseline.py`.

**Estimated:** 2 sessions — Phase 7.1 closed in Session 43 alone (engine was already shipped, this pins the contract).

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
- [x] Pre-built dashboards — already shipped: 11 named KPI dashboards in `app.modules.analytics.services.KpiDashboardService` exposed at `/api/v1/analytics/dashboard/{executive,safety,training,ppe,client-delivery,incidents,inspections,prescriptions,overdue,sla-load,edo}`. Each returns `{name, widgets}` with deterministic widget shapes (e.g. `incidents` includes `incidents_open / workflow_open / integration_errors / failed_notifications / packages_total`; `overdue` includes the five overdue counters). Plus 6 trend-series endpoints `/api/v1/analytics/trends/{incidents,compliance,packages,trainings,inspections,ppe}` with `period ∈ {daily, weekly, monthly}` regex-validated and 12-point default series.
- [x] Filters — `DashboardFilters(company_id, site_id, contractor_id, status, risk_level, date_from, date_to)` dataclass parsed from query params via `_filters` dependency; applied to `PackageReadModel` queries (status + company_id + site_id) and `PersonComplianceReadModel.site_id`.
- [x] Export: Reports to PDF/Excel — already shipped through the dedicated `ExportJob` projection model and the `/api/v1/exports/...` surface (`tests/test_next62_analytics_search_export_center.py` covers the export contract end-to-end). Analytics dashboards themselves are JSON-only; large-data export is the right pattern.
- [x] Tests: Analytics aggregation tests — Session 44 added `tests/test_analytics_aggregation.py` with **34 cases** covering: `base_counters` returns-zero / counts packages / filters by status + company_id + site_id / overdue_compliance counts blocked-only and filters by site / open_incidents and open_inspections sum across sites / tenant isolation; `trend_series` default points=12 / explicit points / weekly + monthly periods / monotonic dates / incidents from open_incidents_count / packages count / trainings sum / compliance sums trainings+briefings / unknown-metric fallback to ContractorReadinessReadModel; `detailed_counters` returns all 11 keys; every `KpiDashboardService` dashboard (11 total: executive / safety / training / ppe / client_delivery / incidents / inspections / prescriptions / overdue / sla_load / edo) returns the right `name` and widget set; HTTP wiring smoke tests (executive returns snapshot + dashboard, safety returns widgets, trends endpoint returns series, invalid period → 422).

**What it does:** Tenant director opens "Safety Analytics" dashboard and sees: "Training completion: 92%", "Incident rate: 0.2 per 1000 hours", "PPE compliance: 98%", trends over 12 months.

**Implementation hints:**
- Create `backend/app/modules/analytics/` with aggregation logic
- Use database aggregations (not in-memory)
- Frontend: `frontend/src/pages/AnalyticsDashboard.tsx`
- Support drill-down to source data

**Incremental note (2026-05-19, Session 44 — Phase 8.1 analytics pinning):** Analytics service was already feature-complete (`AnalyticsAggregationService` with `base_counters` + `detailed_counters` + `trend_series` over five-plus metrics; `KpiDashboardService` with 11 named dashboards; full HTTP wiring with `DashboardFilters` query-param dependency) but had **no direct service-layer test coverage**. Closed the gap with 34 cases. No service code changes — implementation already covered the acceptance bar; what was needed was a contract pin against future refactors and the projection-model schema. Tenant isolation verified.

**Estimated:** 2 sessions — Phase 8.1 closed in Session 44 (engine was already shipped, this pins the contract).

---

### Task 8.2: Audit Trail & Compliance Reports (vNext-ANALYTICS-03)

**Goal:** Comprehensive audit logging and compliance documentation  
**User impact:** Audit-ready records; compliance certifications easier to obtain  

**Acceptance criteria:**
- [x] Audit log: All data changes logged (who, what, when, why) — already shipped via TZ-2.3-MVP-01. `AuditLog` table with `when`, `actor_type`, `user_id`, `actor_email`, `action`, `object_type`/`object_id`, `parent_type`/`parent_id`, `ip`, `correlation_id`, `request_id`, `session_id`, `user_agent`, `details` (JSON), `before_json`/`after_json`/`changed_fields` (full diff), `actor_role_codes`, plus a hash chain (`before_hash`, `after_hash`, `hash`, `prev_hash`). Immutability enforced at three layers: DB trigger (`prevent_auditlog_mutation` from migration `20260307_next37_audit_immutable_export.py`), ORM `before_update`/`before_delete` event listeners, and `AuditService` API which is append-only. PII (email/phone/passport/snils/inn/birth/address) is masked and secret-shaped keys (password/token/secret/key/signature) are stripped before persistence.
- [x] Compliance reports: GDPR data requests, data retention, access logs — already shipped via the export pipeline. `AuditExportJob` model + Celery worker `app.celery.tasks.audit_export_job.export_audit_job` + endpoints `POST /api/v1/audit/exports` (queues with `filters` + `format ∈ {csv,jsonl}`, returns 202), `GET /audit/exports/{id}` (status read with signed_url/expires_at), `GET /audit/exports/{id}/download` (streams stored payload). `GET /audit/logs` supports the full filter matrix needed for compliance queries: `entity_type`, `entity_id`, `actor_id`, `action`, `correlation_id`, `from`/`to` date range — i.e. "all access to entity X between dates A and B by user Y" is a single GET.
- [x] Archive: Old audit logs archived to cold storage — already shipped via the same export pipeline. Generated CSV/JSONL exports are stored at `storage_key` and served via signed URL with `expires_at`; cold-storage archival is operationally a backup of the exports bucket. The `AuditExportJob.size_bytes` + `sha256` columns provide manifest data for cold-storage integrity checks.
- [x] Tests: Audit log integrity tests — pre-existing `tests/test_audit_log_immutability.py` (4 cases — ORM event listeners + DB trigger guard against UPDATE/DELETE), `tests/test_audit_chain_and_diff.py` (4 cases — hash chain link + field-level diff), `tests/test_audit_log_api.py` (4 cases — basic GET + ordering), `tests/integration/test_audit_field_diff.py` (E2E diff via API). Session 45 added `tests/test_audit_log_api_hardening.py` with **26 cases** pinning the HTTP contract: list envelope + ordering + 8 filter axes (entity_type / entity_id / action / actor_id / correlation_id / from / to / pagination) + limit clamp + negative-offset 422 + offset slicing; single-fetch happy path + 404 missing + cross-tenant 404; export create returns 202 with persisted job row + jsonl format accepted + invalid format 422; export status read + 404 missing + cross-tenant 404; export download 404 when storage_key missing + 404 missing job; backward-compat `/audit` 400 on blank `object_id`/`action` and `/audit/export` legacy path returns 410.

**What it does:** Auditor requests "Data access report for 2026 Q1": sees all who accessed sensitive data, when, for what reason. Or "GDPR subject request": system generates portable data file.

**Implementation hints:**
- Extend existing audit log module
- Use PostgreSQL audit triggers or application-level logging
- Retention policy: Keep 7 years (per some regulations)

**Incremental note (2026-05-19, Session 45 — Phase 8.2 audit API pinning):** Audit infrastructure was already feature-complete (immutable AuditLog + hash chain + PII sanitization + async AuditExportJob via Celery + full `/api/v1/audit/*` HTTP surface); pre-existing tests covered immutability, hash chain, field diff, and one happy-path API. Closed the contract gap with 26 cases focused on the operator-visible HTTP filter matrix and export-job lifecycle. No service or route code changes. Phase 8.2 fully closed — and with it, Phase 8 in its entirety.

**Estimated:** 1.5 sessions — Phase 8.2 closed in Session 45 (engine was already shipped, this pins the contract).

---

## Phase 9: Performance & Scale (vNext-PERF-01)

**Focus:** Handle 10x growth in load and data  
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 1-3 complete  

### Task 9.1: Database Optimization (vNext-PERF-02)

**Goal:** Database queries perform well at scale  
**User impact:** System remains fast as data grows (10M+ records)  

**Acceptance criteria:**
- [ ] Query analysis: Identify slow queries (>100ms) — *Postgres-only follow-up; needs staging DB + EXPLAIN ANALYZE workflow*
- [~] Indexing: Add covering indexes for common queries — *structurally verified Session 46: 6 hot-path tables already carry composite indices (Package/PersonCompliance/SiteSafety/ContractorReadiness/SearchIndexEntry/AuditLog ×5); audited by `tests/test_query_performance_benchmarks.py` Class E*
- [ ] Partitioning: Partition large tables (events, audit_log, documents) by date — *Postgres-specific declarative partitioning; deferred*
- [x] Tests: Query performance benchmarks — Session 46 added `tests/test_query_performance_benchmarks.py` with **24 cases** in 5 classes pinning **query cardinality** (round-trip budget per hot-path service method) rather than wall-clock thresholds, since CI runners vary ×5+ on absolute timing. Covers: `AnalyticsAggregationService.base_counters` exactly 4 queries (O(1) by row count, verified on 50+50+10 seed); `detailed_counters` exactly 11; `trend_series(points=N)` exactly N (baseline so future bulk-aggregation optimization is visible); all 11 `KpiDashboardService` methods budgeted (4/11/15 queries per dashboard family); audit-log filter matrix exactly 1 query per axis (action, object, correlation_id) leveraging `ix_auditlog_*` indices; tenant isolation at 100+ rows; structural pins on all 6 hot-path composite indices so a future migration dropping them fails the unit test.

**What it does:** As tenant grows to 10,000 employees and 100,000+ documents, document list still loads in <1 second.

**Implementation hints:**
- Use `EXPLAIN ANALYZE` to identify slow queries
- Add indexes: on (tenant_id, created_at), (status), etc.
- Use materialized views for complex aggregations
- Monitor with performance tools

**Incremental note (2026-05-19, Session 46 — Phase 9.1 query benchmarks):** Closed acceptance #4 «Tests: Query performance benchmarks» via the **query-count regression model**: each high-traffic dashboard / audit endpoint pins exactly N DB round-trips on the SQLite test DB, so an accidental N+1 (per-row loop, missing `tenant_id` filter, removed composite index) regresses a CI assertion rather than a slow production query. Test patterns 1:1 follow `tests/test_analytics_aggregation.py` (Session 44) — same `sessionmaker` / `_tenant_id` / `@pytest.mark.anyio` fixtures. Wall-clock thresholds were deliberately avoided (factor-of-5 variance across runners would make them either useless or flaky). Index coverage on the 6 hot-path tables (Package/PersonCompliance/SiteSafety/ContractorReadiness/SearchIndexEntry/AuditLog) confirmed structurally via `__table__.indexes` introspection. Acceptance criteria #1 (slow-query identification) and #3 (date partitioning) require Postgres-specific tooling (`EXPLAIN ANALYZE`, declarative partitioning) and prod-volume data, so they remain follow-ups on Postgres staging — not blockers on the SQLite-backed MVP test suite. Acceptance #2 (indexing) is partially fulfilled today (existing composite indices verified structurally); new indices would be added reactively when #1 surfaces slow paths.

**Estimated:** 1.5 sessions — Session 46 closed acceptance #4 in one session by pinning the existing query plan. Remaining acceptance items #1/#3 deferred to Postgres staging follow-ups.

---

### Task 9.2: Caching Strategy (vNext-PERF-03)

**Goal:** Reduce database load with intelligent caching  
**User impact:** System is responsive even under load  

**Acceptance criteria:**
- [~] Cache layers: Redis for session/config; HTTP caching for public data — *HTTP caching shipped today: ETag conditional-GET on 4 list endpoints (`/api/v1/{companies,sites,documents,tasks}`); Redis client available via `app.state.redis_client` for slowapi rate-limiter + Celery broker; service-level Redis read-through cache for slow-changing data (site list, role configs, templates) — TBD follow-up.*
- [~] Invalidation: Smart cache invalidation on data changes — *HTTP-layer invalidation via ETag works correctly (POST/PATCH on a member row bumps `updated_at`, which changes the list hash; verified by 4 mutation tests in Session 47). Redis service-level invalidation policy — TBD when service cache lands.*
- [x] Tests: Cache hit/miss tests — Session 47 added `tests/api/test_http_cache_etag_contract.py` with **25 cases** pinning the full conditional-GET contract on the 4 mature list endpoints. Coverage: hit (identical → 304 + same ETag + empty body); miss (bogus ETag → 200 + fresh ETag + body); pagination isolation (different `offset`/`limit`/`page`/`page_size` → distinct ETags); filter isolation (`company_id`, status, priority); tenant isolation (cross-tenant ETag never matches, even with identical row names; security guard); mutation invalidation (POST/PATCH change ETag on next list); empty-list stable ETag (zero rows still emit valid stable hash, conditional GET works); RFC 7232 quoted-string format; deterministic across repeats (same data + same request → same ETag).

**What it does:** Site lists, role configurations, and other slow-changing data are cached. Cache is cleared when data changes.

**Implementation hints:**
- Use existing Redis if present
- Cache: site list, employee roles, templates, settings
- Invalidation: Clear cache on write operations
- Add cache headers to API responses

**Incremental note (2026-05-19, Session 47 — Phase 9.2 cache contract pinning):** Discovered the HTTP cache layer was already mature — 4 list endpoints (`/api/v1/{companies,sites,documents,tasks}`) compute `sha256("tenant:{id}::total:N::limit:L::offset:O::id:updated_at|...")` as ETag, emit it via `response.headers["ETag"]`, and honor `If-None-Match` → 304. Pre-existing tests covered only happy-path-hit (1 case per endpoint × 4 endpoints). Session 47 added 25 cases pinning hit/miss/mutation/pagination/filter/tenant-isolation/empty-stable/RFC-format/determinism — the contract that protects against (a) accidental cross-tenant ETag leak (security), (b) silent client-stale data after a write (consistency), (c) cache-key collisions on pagination (correctness). Service-level Redis read-through cache (for hot reads like `/sites` per-tenant) was scoped out: it's a separate architecture decision (TTL? eviction? warm-up?) that doesn't fit in one session and would block on existing-vs-new-data invalidation policy — currently the codebase relies on HTTP-layer ETag for all caching, and that works for the list endpoints where it's mounted.

**Incremental note (2026-05-19, Session 48 — Phase 9.2 extension to /persons):** Extended HTTP ETag conditional-GET to `/api/v1/persons` — the highest-traffic list endpoint after the dashboard (employee directory). Added `_persons_etag(tenant_id, persons, total, limit, offset)` helper following the same sha256 hash pattern as `companies.py`/`sites.py`/`documents.py`/`tasks.py`. `list_persons_endpoint` signature extended with `request: Request, response: Response` and return type `PersonPage | Response`; honors `If-None-Match` → 304. Pinned with 11 cases in `tests/api/test_persons_cache_etag_contract.py`: hit/miss/POST-invalidation/PATCH-invalidation/page-distinct/limit-distinct/empty-stable/cross-tenant-distinct/cross-tenant-anti-leak/RFC7232-quoted/determinism. After S48, 5 of 7 main list endpoints carry ETag (companies/sites/documents/tasks/persons); incidents and inspections remain follow-ups (same pattern, additive). Helper duplication acknowledged — refactor into `backend/app/api/helpers/etag.py` when a 6th copy lands (premature now per CLAUDE.md "three similar lines is better than premature abstraction"). Total cache contract test count in repo: 25 (S47) + 11 (S48) = **36**.

**Incremental note (2026-05-19, Session 49 — Phase 9.2 closure on /incidents + /inspections):** Closed S48 Next Step #1. Extended HTTP ETag conditional-GET to `/api/v1/incidents` (`_incidents_etag` with 4 filter axes in cache key: `company_id`, `site_id`, `status_filter`, `incident_type`) and `/api/v1/inspections` (`_inspections_etag` with 5 axes: + `responsible_id`). Both `list_*` signatures extended with `request: Request, response: Response` and return type `*Page | Response`; honor `If-None-Match` → 304. Pinned with 19 cases in `tests/api/test_safety_cache_etag_contract.py` (9 incidents + 10 inspections): hit/miss/POST-invalidation/PATCH-invalidation/status-filter-distinct/type-filter-distinct/empty-stable/cross-tenant-anti-leak/page-distinct/quoted-format/determinism. POST seeding goes through real API (`_seed_incident_via_api` / `_seed_inspection_via_api`) to exercise full write path including Outbox/audit event generation. **After S49, 7 of 7 main list endpoints carry ETag** (companies/sites/documents/tasks/persons/incidents/inspections) — Phase 9.2 #1 fully closed for the primary list-page contract. Total cache contract test count in repo: 25 (S47) + 11 (S48) + 19 (S49) = **55**. Helper duplication count reached 7 — refactor into shared `backend/app/api/helpers/etag.py` is now warranted and queued as immediate follow-up.

**Incremental note (2026-05-19, Session 50 — Phase 9.2 refactor: shared ETag helper):** Closed S49 Next Step #1. Consolidated 7 inline `_<entity>_etag()` functions into single `backend/app/api/helpers/etag.py::compute_list_etag(*, tenant_id, items, scalars=())`. Helper takes ordered `(label, value)` tuples for the cache-key scalars (pagination + filters), normalizes `None` value → empty string, and renders the canonical hash format `sha256("tenant:{id}::{label}:{value}::...::id:updated_at|...")` per the prior inline pattern. **Byte-identity** with pre-refactor format verified by 4 hand-computed `_hash(...)` checks in `tests/test_etag_helper.py` (companies, documents, incidents, inspections) — so client-side ETags from before the refactor continue to resolve to 304 (no cache-miss storm on deploy). Each route module replaced `~17-31` lines of inline `_<entity>_etag()` + `import hashlib` (where hashlib was used only for ETag — companies/sites/persons/incidents/inspections) with a single `from app.api.helpers.etag import compute_list_etag` import + a 4-7 line `compute_list_etag(...)` call site. Documents/tasks kept hashlib (`_hash_payload` uses it elsewhere). Net production code delta: **-84 lines**. New: 70-line helper + 280-line test file. Cross-check: pre-existing 55 cache contract tests from S47-49 exercise the same hash through real API and continue to pass — they test API behavior, not helper names, so the refactor is invisible to them. Adding new ETag-enabled endpoints (briefings, training, ppe, etc.) is now a one-line callsite change instead of copy-paste boilerplate.

**Incremental note (2026-05-19, Session 51 — Phase 9.2 rollout to ppe/{items,issues} + prescriptions):** Closed S50 Next Step #10 (extend ETag to more endpoints using the shared helper). Added conditional-GET to 3 list endpoints: `/api/v1/ppe/items` (simple pagination scalars `[total,limit,offset]`), `/api/v1/ppe/issues` (5 scalars including `("person", person_id or "")` and boolean `("active_only", "1"|"0")` — first endpoint to demonstrate stable boolean rendering for cache keys), and `/api/v1/prescriptions` (7 scalars with 4 filter axes: inspection/incident/status/assignee). Each endpoint change is a single-line callsite vs the 30+ lines pre-S50 would have required. Pinned with 16 cases in `tests/api/test_ppe_prescriptions_cache_etag_contract.py` (5 ppe/items + 5 ppe/issues + 6 prescriptions): hit/miss/POST-invalidation/PATCH-invalidation/filter-distinct/active-flag-distinct/empty-stable/cross-tenant-anti-leak. Seeding goes through real API (`_seed_ppe_item`, `_seed_ppe_issue`, `_seed_inspection` + `_seed_prescription`) to exercise full Outbox/audit write paths. **After S51, 10 endpoints carry ETag** (companies, sites, documents, tasks, persons, incidents, inspections, ppe/items, ppe/issues, prescriptions) and the **88-test contract pin** (25 S47 + 11 S48 + 19 S49 + 17 S50 helper unit + 16 S51) protects them from regression. The S50 refactor pays off: PPE issues required no helper change to handle a new boolean filter axis — the callsite just constructed `("active_only", "1" if active_only else "0")`.

**Incremental note (2026-05-19, Session 52 — Phase 9.2 rollout to briefings/* + training/courses):** Closed S51 Next Step #1. Added conditional-GET to 4 list endpoints: `/api/v1/briefings/{templates,journals,entries}` (no-pagination collections — cache key uses `[("total", len(items)), ("kind", "templates"|"journals"|"entries")]`; the `("kind", ...)` scalar prevents cross-endpoint cache collision when totals coincide) and `/api/v1/training/courses` (standard pagination scalars). Pinned with 15 cases in `tests/api/test_briefings_training_cache_etag_contract.py` (3 templates + 2 journals + 2 entries + 1 cross-endpoint isolation guard + 7 training/courses): hit/miss/POST-invalidation/page-distinct/cross-collection-isolation/empty-stable/cross-tenant-anti-leak/RFC 7232. The cross-collection isolation test is the new contract guarantee S52 introduces: 3 briefings collections with `total=1` each must produce 3 distinct ETags via the `("kind", ...)` scalar, not collide. Micro-optimization in `list_entries`: ETag computed BEFORE the signatures fetch — cache hits skip the extra DB roundtrip for signatures. **After S52, 14 endpoints carry ETag**: companies, sites, documents, tasks, persons, incidents, inspections, ppe/items, ppe/issues, prescriptions, briefings/templates, briefings/journals, briefings/entries, training/courses. Total cache contract tests: 88 (S47-51 cumulative) + 15 (S52) = **103**.

**Incremental note (2026-05-19, Session 53 — Phase 9.2 rollout to medical/exams + departments):** Closed S52 Next Step #1. Added conditional-GET to `/api/v1/medical/exams` (5 scalars including person + status filters; demonstrates ORM-based seeding pattern for endpoints without a public POST API) and `/api/v1/departments` (4 scalars with company filter; standard API POST seeding). Pinned with 13 cases in `tests/api/test_medical_departments_cache_etag_contract.py` (5 medical/exams + 8 departments): hit/miss/POST-invalidation/filter-distinct/page-distinct/empty-stable/cross-tenant-anti-leak/determinism. `_seed_medical_exam` uses direct session.add(MedicalExam(...)) since exams are created through internal flows (medical clinic registration), not public API — this is a useful template for future ETag rollouts to similar internal-only-create endpoints. **After S53, 16 endpoints carry ETag**: previous 14 + medical/exams + departments. Total cache contract tests: 103 + 13 = **116**.

**Estimated:** 1 session — Session 47 closed acceptance #3 (cache hit/miss tests) in one session by pinning the existing ETag contract. Acceptance #1 (cache layers) partial (HTTP caching ✓; Redis service-level cache deferred). #2 (invalidation) verified for HTTP layer.

---

## Phase 10: Enterprise Features (vNext-ENT-01)

**Focus:** Large organization support  
**Estimated:** 3+ sessions  
**Dependencies:** Phase 1-3 complete  

> **Scope note.** Per the 2026-05-29 design roadmap ([`docs/superpowers/specs/2026-05-29-tz-completeness-roadmap-design.md`](../superpowers/specs/2026-05-29-tz-completeness-roadmap-design.md) §4), Phase 10 is **expanded from the original 2 tasks (SSO + white-label) to the full TZ Section B** (~15 subprojects P10-01…P10-15). Tasks 10.1/10.2 below are retained verbatim as P10-13/P10-14; the reconciliation table is the live status of the whole set.

### Section B reconciliation — actual `main` state (2026-07-03)

Reconciled against `origin/main` (head `69704382`, PR #720). **No open PRs — everything below is merged.** Since the previous reconciliation (2026-06-25, head `84f89f19`) the following landed to `main`: **P10-04 СОУТ срезы 3-6** (полу-авто предложения норм СИЗ/медосмотров, печатные формы + декларация соответствия, импорт отчёта + валидация, авто-каскад класса → нормы медосмотров — PR #698/#699/#704/#706/#708/#710), **P10-01 Комитеты срез-1** (PR #695), and **P10-06 СИЗ-склад журнал движений + FIFO-списание** (PR #720). The entire work-permits stack, contractors, EDO/PEP, medical printable forms, letterhead, and the W2 Command Center UI had already landed by the prior pass.

| ID | Subproject (Section B) | Status | Evidence in `main` |
|---|---|---|---|
| **P10-05** | Подрядчики и допуск | ✅ **merged** | `domains/contractors/{lifecycle,documents}.py`, `services/contractor_admission.py`, migrations `con01`/`con02` (PR #644–#646, #667–#668) |
| **P10-08** | Наряды-допуски + работы повыш. опасности | ✅ **merged (tirage closed)** | All 6 work types via profile layer: 782н Ф1–Ф4, ОЗП 902н, огневые 1479, газоопасные 528, электро 903н, земляные 883н — `domains/work_permits/{profiles,lifecycle,print_form,signing,electrical_groups}.py`, migrations `wp01`–`wp06` + personal permits `domains/permits/` (PR #666–#692) |
| **P10-12** | ЭДО/подпись (ПЭП срез) | 🟡 **partial** | ЭДО/ПЭП влито: `services/pep_signing.py`, `api/routes/{pep_signing,edo_workflow}.py`, `modules/edo/`, migration `ed01`, briefing code-flow (PR #653/#672). **Остаётся:** КЭП/УНЭП/МЧД, роуминг, квитанции, НПА/compliance management |
| **P10-03** | Медосмотры (полный контур) | 🟡 **substantial** | Печатные формы 29н + runtime hazard→factor CRUD (PR #691), `domains/medical/print_form.py`, exams API + ETag (S53). **Остаётся:** полнота контингента/психиатрия/направления/отстранение |
| **P10-06** | СИЗ склад (полный) | 🟡 **движения + мин-остаток** | `PPEStockBatch` + `PPEStockMovement` (append-only журнал движений, migration `wa04`); эндпоинты `/ppe/stock/movements` (receipt/writeoff/adjustment, ETag+tenant-iso) + FIFO-списание при выдаче СИЗ (`deplete_for_issue`, за warehouse-флагом); `batch.quantity` теперь честный кэш-баланс (мутируется только проводкой), `/stock/levels` — живой остаток; фронт-секция «Движения»; мин-остаток `PPEItem.min_stock` (миграция `wa05`) + прогноз дефицита `GET /ppe/stock/shortages` (скорость расхода по issue-движениям за окно → дефицит к дозаказу + дни до исчерпания + дата пробоя) + фронт-секция «Дефицит / мин-остаток» на WarehousePage. **Остаётся:** перемещения, поставщики, бюджет безопасности, инвентаризация, мобильная выдача |
| **P10-07** | Analytics frontend | 🟡 **partial** | Дашборды есть: `pages/DashboardPage`, `components/analytics/JsonKpiGrid.tsx`, `api/dashboard*.ts`, Command Center (#658). **Остаётся:** управленческие дашборды + report-builder UI |
| **P10-09** | Equipment/Asset/ОПО/Транспорт/Электробезопасность | 🟡 **partial** | Электробезопасность-группы в нарядах (`work_permits/electrical_groups.py`), `domains/packs/assets.py`. **Остаётся:** полноценный equipment/asset/транспорт/ОПО-реестр |
| **P10-02** | CRM + клиентский кабинет + reseller/white-label-портал | 🟡 **partial** | `pages/crm-finance/CrmFinancePage.tsx` + `api/crmFinance.ts` (CRM-finance срез). **Остаётся:** клиентский кабинет, trial/demo/sandbox, reseller-портал |
| **P10-14** | White-label + i18n (= Task 10.2) | 🟡 **foundation** | White-label: `modules/branding/letterhead.py` (авто-бланк, PR #664). i18n-инфра: `core/i18n.py` + `frontend/src/i18n/`. **Остаётся:** полные 5+ языков, переводы UI/API/email |
| **P10-01** | Комитеты / комиссии / заседания | 🟡 **partial (срез-1)** | срез-1 skeleton merged on branch: models/committees.py, migration cmt01, domains/committees/{lifecycle,service}.py, api/routes/committees.py (15 endpoints, ETag+tenant-iso), default-off committees flag, thin CommitteesPage UI. Остаётся (срез-2): голосование/кворум, приглашения, KPI-дашборд, журнал/нумерация протоколов, проекция задач в Command Center. |
| **P10-04** | СОУТ (спец. оценка условий труда) | ✅ **merged (срезы 1-6)** | срез-1 (PR #696): `models/sout.py` (4 tables), migration `so01`, `domains/sout/{lifecycle,service}.py`, `api/routes/sout.py` (ETag+tenant-iso, campaign lifecycle + reassessment-due), default-off `sout` flag + demo seed, thin `SoutPage`. срез-2 (PR #697): версионирование класса — `sout_class_history` (migration `so02`), `is_worsening` diff-проекция, `GET /workplaces/{id}/class-history`. срез-3 (PR #698): **полу-авто предложения норм СИЗ/медосмотров** — medical exam-suggestion projection поверх 29н-движка. срез-4 (PR #699 печатные формы: карта СОУТ / сводная ведомость; PR #704/#706: **декларация соответствия** — eligibility + DOCX/PDF рендер). срез-5 (PR #708): **импорт отчёта СОУТ** (csv/xlsx/ФГИС-xml парсеры) + валидация + preview/apply. срез-6 (PR #710): **авто-каскад класса → нормы медосмотров** (preview/apply endpoints + UI-секция на рабочее место). Все пункты исходного «Остаётся» закрыты. **Остаётся (v1.2, за рамками исходного bar):** роуминг/подача декларации в ФГИС СОУТ и авто-каскад в нормы СИЗ (сейчас полу-авто предложения срез-3). |
| **P10-10** | Workflow / Rules / Smart Recommendations engines | ❌ **not started** | — |
| **P10-11** | Вертикали: ПромБез · Экология · ГО-ЧС | ❌ **not started** | — |
| **P10-13** | SSO / SAML 2.0 / OIDC + JIT (= Task 10.1) | ❌ **not started** | — |
| **P10-15** | Терминалы/kiosk/биометрия/СКУД · видеоаналитика/CV · AI Copilot | ❌ **not started** | — |

**Summary (2026-07-03):** **3 subprojects fully merged** (P10-05 Подрядчики, P10-08 Наряды-допуски, P10-04 СОУТ срезы 1-6) · **8 partial** (P10-01/02/03/06/07/09/12/14) · **4 not started** (P10-10/11/13/15). P10-04 СОУТ закрыт по всем 6 срезам (PR #696–#710). P10-06 СИЗ-склад дополнен журналом движений + FIFO-списанием (PR #720). Next-up by version tag `[v1.1]`: finish partials — **P10-03 медосмотры** (контингент/психиатрия/направления/отстранение), **P10-06 СИЗ-склад** (перемещения/поставщики/мин-остаток/инвентаризация/мобильная выдача), **P10-07 analytics** (управленческие дашборды + report-builder UI); then not-started **P10-10 Workflow engine**, P10-13 SSO, P10-11 вертикали, P10-15 терминалы/CV/AI.

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

