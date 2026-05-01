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
| Phase 0: Release Blockers | P0 | TZ-1.1 baseline re-verification | 1 session | 🔴 CRITICAL |
| Phase 1: Architectural Foundation | P1 | Role-based workspaces, RBAC refinements, tenant isolation | 2-3 sessions | 📋 Planned |
| Phase 2: Operational Dashboard | P1 | Command Center, health checks, operational visibility | 2-3 sessions | 📋 Planned |
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
**Estimated:** 2-3 sessions  
**Dependencies:** Phase 0 complete  

### Task 1.1: Role-Based Workspaces (vNext-IA-01)

**Goal:** Replace generic dashboard with role-specific views  
**User impact:** Each role (OT specialist, manager, trainer, warehouse keeper, etc.) sees custom workspace with KPIs, quick actions, and tasks  

**Acceptance criteria:**
- [ ] Backend: `/api/v1/users/workspace` endpoint returns role-specific dashboard config
- [ ] Frontend: Role-detection logic in `AppRouter.tsx` routes users to appropriate workspace
- [ ] Support 15+ role types (per SPEC sec. 4.2): tenant owner, admin, OT specialist, manager, trainer, student, auditor, contractor, client, etc.
- [ ] Each workspace includes: KPIs, overdue items, today's tasks, quick actions, recent events, calendar widget, drafts
- [ ] Tests: 20+ unit + integration tests for role detection and workspace configuration
- [ ] No breaking changes to existing routes

**What it does:** Instead of a generic "Dashboard" page, users land on a workspace tailored to their role. OT specialist sees risk/PPE/training tasks; manager sees team KPIs and overdue items; trainer sees class assignments and student progress.

**Implementation hints:**
- Extend `RoleEnum` in `backend/app/models/roles.py` if needed
- Create `backend/app/modules/workspace/` module with config builder
- Add `WorkspaceDTO` to responses
- Create frontend pages: `frontend/src/pages/workspaces/{RoleName}Workspace.tsx`
- Feature flag: `FEATURE_ROLE_BASED_WORKSPACE=true`

**Estimated:** 1.5 sessions

---

### Task 1.2: RBAC Engine Hardening (vNext-SEC-01)

**Goal:** Expand RBAC/ABAC for granular module access control  
**User impact:** Administrators can enable/disable modules per role; operators see only their permitted modules  

**Acceptance criteria:**
- [ ] Module-level permissions: `modules.risk`, `modules.ppe`, `modules.training`, `modules.documents`, etc.
- [ ] Backend: RBAC engine checks module permission before exposing endpoints
- [ ] Frontend: Nav/sidebar filters out unavailable modules based on user permissions
- [ ] Tests: Negative tests for cross-module boundary violations (OT specialist cannot access admin endpoints)
- [ ] No breaking changes to existing permission checks

**What it does:** Administrators can create custom roles with selective module access: e.g., "Field Auditor" sees only inspection + incident modules; "Trainer" sees only training + briefing modules; "Warehouse" sees only PPE module.

**Implementation hints:**
- Extend `backend/app/modules/rbac_abac/engine.py` with module-level policy
- Add permission definitions: `backend/app/core/permissions.py` (if not already)
- Update `AbacPolicy.evaluate()` to check `resource.module` against role permissions
- Create migration: add `modules` JSONB column to `roles` table

**Estimated:** 1 session

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

### Task 2.1: Command Center / Operational Dashboard (vNext-OPS-01)

**Goal:** Single screen showing all critical alerts and KPIs  
**User impact:** Tenant admin/operator can spot issues without navigating 10+ modules  

**Acceptance criteria:**
- [ ] Backend: `/api/v1/operational/dashboard` aggregates alerts from all modules
- [ ] Frontend: Dashboard page with widgets: critical overdue items, blocked approvals, problematic documents, integration errors, high-risk sites, unclosed prescriptions, expiring trainings/medicals/PPE, offline conflicts, unassigned tasks, tenant health warnings
- [ ] Real-time updates: WebSocket or polling every 30s
- [ ] Tests: 15+ integration tests for alert aggregation logic
- [ ] Performance: Dashboard loads in <2 seconds even with 1000+ items

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
- [ ] Backend: `/api/v1/health/comprehensive` checks: database, integrations, file storage, email, workers, external APIs
- [ ] Frontend: Health status page with drill-down per service
- [ ] Alerts: Send notifications if critical services degrade
- [ ] Tests: Mock failures and verify correct alerting

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
- [ ] Backend: Data quality rules engine (`backend/app/modules/data_quality/`)
- [ ] Rules cover: missing mandatory fields, logical conflicts, duplicates, broken relationships, integration mismatches, expired records, docs not ready for generation, permits not valid for contractors
- [ ] Dashboard: `/api/v1/data-quality/report` shows tenant completeness %, critical issues, affected objects/employees
- [ ] Tests: 20+ rule tests covering positive and negative cases

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
