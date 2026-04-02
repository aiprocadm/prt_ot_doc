# Enterprise Usability & Operational Hardening Plan
**Version:** 1.0  
**Start Date:** March 24, 2026  
**Target Timeline:** 8–12 weeks  
**Owner:** Senior Full-Stack Engineer / Platform Hardening Lead  

---

## Mission Statement

Transform the platform from **strong architectural skeleton** to **corporate-ready daily-use system**.

Do **not** rewrite working functions. **Do** harden, unify, and eliminate non-production paths.

### Hard Rules

1. ✅ **No massive rewrites** — preserve existing working flows
2. ✅ **Tenant-safe** — every operation must respect tenant context
3. ✅ **Permission-safe** — authz checks consistent and complete
4. ✅ **Audit-aware** — sensitive actions logged
5. ✅ **Documented** — gaps and decisions recorded
6. ✅ **Tested** — new/changed logic verified
7. ✅ **No feature debt** — stub/mock/fallback behavior isolated and explicit

---

## Phase 1: Enterprise Usability & Operational Audit

**Goal:** Create comprehensive factual audit of current state.

**Deliverables:**
- ✅ `docs/ENTERPRISE_USABILITY_AUDIT.md` (baseline facts)
- ✅ Confirmed findings on non-production paths
- ✅ Verified operational pages and gaps
- ✅ Architecture risk inventory
- ✅ Test coverage assessment

**Output Files:**
- `docs/ENTERPRISE_USABILITY_AUDIT.md` — **COMPLETED**
- `docs/ENTERPRISE_USABILITY_PLAN.md` — this document
- `docs/ENTERPRISE_USABILITY_COMPLETION_REPORT.md` — after each phase
- `docs/ENTERPRISE_USABILITY_REMAINING_GAPS.md` — running inventory

**Effort:** 1–2 weeks (parallel with planning)

---

## Phase 2: Platform Consistency Hardening

**Goal:** Make platform behavior uniform across modules. This is the foundation for trust.

### Backend Consistency Tasks

**2.1. Tenant Context Enforcement**
- [ ] Audit every business endpoint for tenant context extraction
- [ ] Normalize tenant header/claim parsing (single source of truth)
- [ ] Ensure all queries filter by tenant
- [ ] Ensure all mutations validate tenant ownership
- [ ] Ensure background jobs preserve tenant context
- [ ] Add decorator/middleware to enforce tenant presence
- [ ] Test: tenant isolation verification tests

**File Focus:** `backend/app/api/v1/router.py`, route handlers

**2.2. Permission Check Normalization**
- [ ] Inventory all permission checks across read/write/bulk/export/search
- [ ] Standardize permission check syntax (single pattern)
- [ ] Create permission checker helper library
- [ ] Normalize forbidden error responses (consistent HTTP 403 format)
- [ ] Test: permission check correctness tests (read, write, bulk, export, search)

**File Focus:** `backend/app/api/routes/*.py`, permission logic

**2.3. Structured Error Format**
- [ ] Define standard error envelope (error_code, message, field, details, correlation_id, timestamp)
- [ ] Replace ad-hoc error returns with structured format
- [ ] Create error builder helpers
- [ ] Test: error format consistency tests

**File Focus:** All route handlers, error handling

**2.4. Correlation ID Propagation**
- [ ] Generate correlation_id for every request
- [ ] Propagate correlation_id to all background jobs
- [ ] Propagate correlation_id across service calls
- [ ] Log correlation_id in every log entry
- [ ] Return correlation_id in error responses
- [ ] Test: correlation_id tracing tests

**File Focus:** Middleware, Celery tasks, service layers

**2.5. Audit Coverage for Sensitive Actions**
- [ ] Identify sensitive actions (approve, sign, delete, bulk update, etc.)
- [ ] Add audit log entry for each sensitive action
- [ ] Include: user, tenant, action, object, changes, timestamp, correlation_id
- [ ] Create audit query API for compliance/admin
- [ ] Test: audit logging tests

**File Focus:** `backend/app/services/audit.py` (create if needed), all sensitive endpoints

### Frontend Consistency Tasks

**2.6. Route-Level Permission Awareness**
- [ ] Extract routes requiring specific permissions
- [ ] Add permission check before route render
- [ ] Hide forbidden routes from navigation
- [ ] Return permission-denied page if user navigates directly
- [ ] Test: route permission tests

**File Focus:** `frontend/router.ts`, route definitions

**2.7. Action-Level Permission Awareness**
- [ ] Audit every button/menu action for permission requirement
- [ ] Add permission check before action enable
- [ ] Hide forbidden actions (not just disable)
- [ ] Show reason for disabled actions (tooltip)
- [ ] Test: action visibility tests

**File Focus:** All page components, action handlers

**2.8. Consistent Loading/Error/Empty States**
- [ ] Create standard state components (Loading, Error, Empty)
- [ ] Apply to all data-fetching pages
- [ ] Standardize loading skeleton/spinner
- [ ] Standardize error message + retry button
- [ ] Standardize empty state message + call-to-action
- [ ] Test: state rendering tests

**File Focus:** All page components, utility components

**2.9. Unsaved-Changes Protection**
- [ ] Identify critical forms (documents, approvals, profile, settings)
- [ ] Add dirty-flag tracking
- [ ] Warn on navigation if unsaved
- [ ] Warn on close if unsaved
- [ ] Test: unsaved-changes protection tests

**File Focus:** Form components, route guards

**Effort:** 3–4 weeks

**Validation:** All endpoints/pages pass consistency test suite.

---

## Phase 3: Role-Based Workspaces / Attention / Tasks / Blockers

**Goal:** Make the platform immediately actionable upon login. Users should see what's urgent, blocked, and due.

### Backend Tasks

**3.1. Role Workspace Projections**
- [ ] Define role-based projections (admin, manager, executor, viewer, etc.)
- [ ] Add `/api/workspaces/{role}` endpoint returning:
  - Recent items
  - Pending actions
  - Urgent items (due soon/overdue)
  - Blocked items + reasons
  - Recommendations
  - Quick links
- [ ] Implement caching strategy (refresh every 5 min or on state change)
- [ ] Test: workspace projection correctness

**3.2. Task Inbox**
- [ ] Create `TaskInbox` aggregate (or extend existing task system)
- [ ] Task types: approve, sign, review, acknowledge, fill, complete, decide
- [ ] Add `/api/tasks/inbox` endpoint returning:
  - All pending tasks for user
  - Task type, priority, due date, context
- [ ] Implement task queries by status, priority, due date
- [ ] Test: task inbox correctness

**3.3. Attention Center**
- [ ] Define "attention event" types (urgent, overdue, blocked, new, exception)
- [ ] Create `/api/attention` endpoint returning:
  - Recent attention events
  - Grouped by severity/category
  - With deep links to resolution
- [ ] Implement event emission when:
  - Document readiness drops
  - Approval blocked
  - Item overdue
  - Data quality issue detected
  - System health degrades
- [ ] Test: attention event emission

**3.4. Blocker & Readiness Surfacing**
- [ ] Define blocker types (data quality, permissions, external wait, system)
- [ ] Create `/api/blockers` endpoint returning:
  - Current blockers by object
  - Reason + recommended action
  - Links to resolution
- [ ] Integrate blocker calculation into document/contractor/employee readiness
- [ ] Test: blocker correctness

**3.5. Recommendation Engine** (light)
- [ ] Create `/api/recommendations` endpoint returning:
  - Suggested next actions (based on role, permissions, current state)
  - Bulk actions opportunities
  - Quick wins (easy completions)
- [ ] Implement simple heuristics (not ML):
  - "Approve X waiting documents"
  - "Update expired Y records"
  - "Download Z template"
- [ ] Test: recommendation correctness

**3.6. Event-Driven Updates**
- [ ] Stream status changes to WebSocket or polling fallback
- [ ] Broadcast attention events to relevant users
- [ ] Update task inbox on external state change
- [ ] Update workspace metrics in real-time
- [ ] Test: event propagation

### Frontend Tasks

**3.7. Dashboard/Landing Page**
- [ ] Create role-specific landing page
- [ ] Display: task inbox, blockers, recent items, recommendations, quick links
- [ ] Use workspace projection from backend
- [ ] Keep primary focus obvious (what's most urgent?)
- [ ] Add drill-down links to full views (all tasks, all blockers, all items)
- [ ] Test: landing page rendering

**3.8. Task Inbox Page**
- [ ] Display all pending tasks
- [ ] Sort by priority, due date, type
- [ ] Bulk actions (approve all, reject all, etc.)
- [ ] Quick action buttons on each task (approve, defer, delegate, reject)
- [ ] Show task context + linked object
- [ ] Test: task inbox UX

**3.9. Blockers & Readiness Page**
- [ ] Display all current blockers by object
- [ ] Show reason + recommended action
- [ ] Show severity/urgency
- [ ] Add bulk resolution actions where applicable
- [ ] Deep links to fix
- [ ] Test: blocker page UX

**3.10. Unseen/New Badge**
- [ ] Track which events/tasks user has seen
- [ ] Show badge on menu/tab if unseen items exist
- [ ] Mark items as seen when user visits
- [ ] Test: seen tracking

**Effort:** 4–5 weeks

**Validation:** User logs in and immediately sees task/blocker/recommendation context.

---

## Phase 4: Document Core as Central Enterprise Engine

**Goal:** Unify document lifecycle into single deterministic, auditable, repeatable engine.

**CRITICAL:** Do not rewrite existing document core (template, replace, preview, PDF, packs). Enhance and centralize.

### Documentation & Design

**4.1. Document Lifecycle Unification**
- [ ] Document lifecycle specification:
  ```
  template selection 
  → readiness assessment 
  → data resolution (replace) 
  → render to PDF 
  → approval request 
  → approval chain 
  → signing decision 
  → EDO/external signing 
  → archive
  ```
- [ ] Specify state machine: Draft → ReadyForApproval → ApprovalInProgress → ReadyForSign → Signed → Archived
- [ ] Specify blocking conditions at each state
- [ ] Specify required metadata at each stage
- [ ] Document in `docs/DOCUMENT_LIFECYCLE_UNIFIED.md`

**4.2. Template Resolution Scope Hierarchy**
- [ ] Specify template priority: system < tenant < company < site
- [ ] API: GET `/api/documents/template/{type}` returns template for context (with resolution explanation)
- [ ] Verify existing template lookup follows priority
- [ ] Document in `docs/TEMPLATE_RESOLUTION_HIERARCHY.md`

### Backend Enhancement

**4.3. Readiness Score Calculation**
- [ ] Define readiness score formula (0–100%):
  - All required replacements provided? (40%)
  - All required approvals obtained? (30%)
  - Document renders without errors? (20%)
  - All required signatures ready? (10%)
- [ ] Implement `/api/documents/{id}/readiness` returning:
  - Overall score
  - Component scores
  - Blocking issues + recommended fixes
  - Estimated time to ready

**4.4. Dependency Map Foundations**
- [ ] Track: NPA → which templates depend on it
- [ ] Track: Template → which documents use it
- [ ] Track: Document → which routes require it
- [ ] Implement `/api/documents/dependency-map` returning dependency graph
- [ ] Use for: impact analysis, bulk updates, verification

**4.5. Deterministic Render Metadata**
- [ ] Persist render snapshot: template version, data version, replacement values, render timestamp
- [ ] Store render metadata in document record
- [ ] Enable: "re-render this document with current data" (idempotent rerun)
- [ ] Implement `/api/documents/{id}/render-history` showing past renders

**4.6. Idempotent Reruns + Progress Reporting**
- [ ] Implement document async job worker:
  - Start job with document ID + target action (render, approve, sign, etc.)
  - Job stores: status, progress %, current step, errors, logs
  - User can query `/api/documents/{id}/job-status` for live progress
  - Rerun same job (same parameters) produces same result
- [ ] Test: idempotency and progress accuracy

**4.7. Document Passport Completeness**
- [ ] Ensure every document record includes:
  - Template metadata
  - Version history
  - Render snapshots
  - Approval chain
  - Sign chain
  - EDO metadata
  - Archive location
  - Lifecycle state
- [ ] API: GET `/api/documents/{id}/passport` returns full document passport

**4.8. Audit Logging for Document Lifecycle**
- [ ] Log: every state transition, every approval, every sign, every EDO interaction
- [ ] Include: correlation_id, user, timestamp, action, changes
- [ ] Implement `/api/documents/{id}/audit` returning full lifecycle audit trail

### Frontend Updates

**4.9. Document Management Dashboard**
- [ ] Create dashboard showing:
  - Draft documents + their readiness scores
  - Documents pending approval + approval status
  - Documents pending signature + signature status
  - Signed/archived documents + links
- [ ] Add bulk actions: approve all, sign all, archive all (where applicable)
- [ ] Show blocker context for non-ready documents
- [ ] Deep links to fix blockers

**4.10. Readiness Transparency**
- [ ] On document view, show readiness score + breakdown
- [ ] Show what's blocking + recommended fix
- [ ] Add "Fix Blocker" action (deep link or inline fix)

**Effort:** 5–6 weeks (parallel with Phase 3)

**Validation:** Document can flow from template → ready → approval → sign → archive deterministically and reproducibly.

---

## Phase 5: Remove Corporate-Blocking Fallback/Stub Paths

**Goal:** Make non-production behavior explicit and isolated. Enable production mode.

**CRITICAL:** This is the biggest enterprise blocker. Do not mask internal fallback as production.

### Isolation & Cleanup

**5.1. Approval/Sign Orchestration**
- [ ] Audit: `backend/app/api/routes/approval_signing_v1.py`
- [ ] Identify: which paths are stub/fallback/internal-only
- [ ] Option A (if possible): Implement real orchestration
- [ ] Option B (if not): Cleanly separate non-production mode
  - Requires: explicit flag `APPROVAL_PROVIDER_MODE=internal` / `external`
  - Requires: clear documentation of capability
  - Requires: separate code path or feature flag
- [ ] Update code + documentation
- [ ] Test: approval orchestration correctness in both modes

**5.2. EDO Workflow Orchestration**
- [ ] Audit: `backend/app/api/routes/edo_workflow.py`
- [ ] Identify: mock/stub paths
- [ ] Option A: Implement real EDO protocol (if provider available)
- [ ] Option B: Cleanly separate non-production mode
- [ ] Update code + documentation
- [ ] Test: EDO workflow correctness

**5.3. Integration Stubs**
- [ ] Audit: `backend/app/services/integrations/stubs.py`
- [ ] Isolate providers: 1С, ЭДО, ФРДО, ЕИСОТ
- [ ] Create provider configuration: which providers are real, which are stubs?
- [ ] Create provider health check: `/api/admin/provider-health` showing:
  - Provider name
  - Mode (real / internal-fallback)
  - Status (healthy / degraded / unavailable)
  - Capability flags
- [ ] Move stub logic to separate module: `backend/app/services/integrations/internal_fallbacks.py`
- [ ] Add: `@internal_fallback` decorator to indicate non-production paths
- [ ] Test: provider configuration and health check

**5.4. Pipeline Step Handlers**
- [ ] Audit: `backend/app/services/pipeline_step_handlers.py`
- [ ] Identify: which handlers depend on fallback/provider
- [ ] Implement real handlers where possible (internal orchestration)
- [ ] For unavoidable fallback: mark with `@internal_fallback` + document reason
- [ ] Update documentation: which pipeline steps are production-ready
- [ ] Test: pipeline step execution correctness

**5.5. Document Job Reporting**
- [ ] Audit: `backend/app/celery/tasks/document_jobs_required.py`
- [ ] Identify: deferred/fallback/internal-only semantics
- [ ] Replace with reliable internal orchestration:
  - Job enqueue → Job status tracking → Job completion + result
  - Retry logic + dead-letter queue
  - Status API: `/api/jobs/{job_id}` showing status, progress, errors
- [ ] Update test: job reporting reliability

**5.6. Feature Flag Cleanup**
- [ ] Inventory all feature flags in codebase
- [ ] For each: is it internal-fallback/stub vs. feature-in-progress?
- [ ] Consolidate: all non-production paths should be clearly marked
- [ ] Document in `docs/PROVIDER_MODE_CAPABILITIES.md`:
  - Which providers are real, which are internal
  - Which features are production-ready
  - Which features are preview/experimental

### Documentation

**5.7. Provider Mode Documentation**
- [ ] Create `docs/PROVIDER_MODE_CAPABILITIES.md` specifying:
  - Mode: `PROVIDER_MODE=internal` vs. `external`
  - Capabilities by provider
  - Limitations and workarounds
  - Upgrade path to real provider
- [ ] Create `docs/INTERNAL_FALLBACK_PATTERNS.md` documenting:
  - Why fallback exists
  - Expected behavior
  - Limitations
  - Plans for real implementation

**Effort:** 4–5 weeks

**Validation:** All non-production code paths isolated/documented. Provider mode diagnostics visible and accurate.

---

## Phase 6: Data Quality + Readiness Blockers

**Goal:** Make data quality part of daily operations. Detect incomplete/missing/expired records early.

### Backend Implementation

**6.1. Data Quality Rules Engine**
- [ ] Define check types:
  - Completeness: required fields present?
  - Relations: required records linked?
  - Expiry: critical dates not exceeded?
  - Conflicts: duplicate/contradictory records?
  - Format: values match expected format?
- [ ] Implement check runner: `/api/admin/data-quality/rules`
  - Executes all checks
  - Returns violations by type/entity/severity
  - Results queryable and filterable
- [ ] Document default rules in `docs/DATA_QUALITY_RULES.md`

**6.2. Entity-Specific Checks**
- [ ] **Employees:**
  - Name + birthday + contact present?
  - Department assigned?
  - Risk category assigned?
  - Required training current?
  - Medical checkup current?
  - PPE assigned and current?
  
- [ ] **Companies/Sites:**
  - Name + location + industry present?
  - Risk category assigned?
  - Key personnel assigned?
  - Required documentation current?
  
- [ ] **Templates/Documents:**
  - Template type + name present?
  - Version/revision tracked?
  - Linked to applicable NPA?
  - Render-able without errors?
  
- [ ] **Training:**
  - Required training defined for roles?
  - Completions tracked?
  - Expiry dates set?
  - Acknowledgement captured?
  
- [ ] **PPE:**
  - Type + designation + issue date present?
  - Expiry date current?
  - Size/fit info recorded?
  - Wearer assigned?
  
- [ ] **Contractors:**
  - Contact info + company present?
  - Insurance/liability docs current?
  - Credentials verified?
  - Access permissions defined?

**6.3. Blocker Calculation**
- [ ] For each entity type, calculate blockers:
  - What's preventing this from being used/approved/signed/archived?
  - Severity level (critical | high | medium | low)
  - Recommended fix
- [ ] Implement blocker API: `/api/blockers?entity_type=...&entity_id=...`
- [ ] Persist blocker history (for trend analysis)

**6.4. Readiness Score**
- [ ] Unified readiness calculation:
  - Sum of required checks passed
  - Weight checks by importance
  - Return score 0–100%
  - Return reasons for incomplete score
- [ ] Scope: employees, companies, documents, training, PPE, contractors
- [ ] Implement: `/api/readiness?entity_type=...&entity_id=...`

**6.5. Event Emission**
- [ ] Emit event when: blocker appears, blocker resolved, readiness score changes
- [ ] Subscribe: dashboard/workspace/attention center to these events
- [ ] Update cached readiness on event

**6.6. Bulk Operations**
- [ ] Add `/api/admin/data-quality/bulk-fix` endpoint:
  - Input: check type + severity + auto-fix rules
  - Output: records modified + audit log
  - Example: "Mark all employees with missing medical checkup as blocked"
- [ ] Implement audit logging for all bulk operations

### Frontend Implementation

**6.7. Data Quality Dashboard**
- [ ] Create admin page: "Data Quality Overview"
  - Violations by entity type
  - Trend chart (violations over time)
  - Top blockers by frequency
  - Quick links to fix records
- [ ] Create entity-specific quality pages:
  - Employees with incomplete profiles
  - Training with missing completions
  - PPE with expired dates
  - Documents with unresolved issues

**6.8. Readiness Indicators**
- [ ] Show readiness score on all entity pages
- [ ] Break down score by component
- [ ] Show blocker tooltip on incomplete entities
- [ ] Add "Fix Blocker" deep link

**Effort:** 3–4 weeks (parallel with Phase 5)

**Validation:** Admin can see complete data quality overview and resolve issues.

---

## Phase 7: Practical PWA / Offline / Field Hardening

**Goal:** Make offline/field workflows genuinely useful, not theoretical.

**CRITICAL:** PWA framework exists. Do NOT rebuild. Enhance based on field requirements.

### Backend Enhancement

**7.1. Bootstrap Expansion**
- [ ] Expand `/api/pwa/bootstrap` payload:
  - ✅ current_user (already present)
  - ✅ route_permissions (already present)
  - ✅ dictionaries (already present)
  - ✅ offline_queue (already present)
  - ✅ sync_state (already present)
  - ✅ diagnostics (already present)
  - 🆕 site/company context
  - 🆕 critical reference data (training types, PPE types, incident types, risk categories)
  - 🆕 recent documents (for offline viewing)
  - 🆕 offline instructions (briefings, safety alerts)
  - 🆕 offline forms (incident report template, checkbox template, comment template)
- [ ] Test: bootstrap payload completeness

**7.2. Offline Data Sync**
- [ ] Define offline-synced entities:
  - Reference data (read-only)
  - User drafts (read-write, conflict resolution on sync)
  - Offline queue (write-only, persisted)
- [ ] Implement incremental sync: only sync changes since last sync
- [ ] Implement conflict resolution: last-write-wins or merge
- [ ] API: `/api/pwa/sync` (POST with local changes, GET current remote state)

**7.3. Draft Persistence**
- [ ] Define draft types: incident, checklist, training-ack, comment, form response
- [ ] Add draft endpoints:
  - POST `/api/drafts` (create/update draft)
  - GET `/api/drafts?type=...&context=...` (list drafts for context)
  - DELETE `/api/drafts/{id}` (discard draft)
- [ ] Include: draft ID, type, context, data, last_modified, sync_status

**7.4. Offline Queue Management**
- [ ] Track queued operations: { id, type, entity, action, data, created_at, retry_count, last_error }
- [ ] Implement: exponential backoff retry (1m, 5m, 15m, 1h, etc.)
- [ ] Implement: dead-letter queue for failed operations (> 3 retries)
- [ ] API: `/api/pwa/offline-queue` (list queued operations)

**7.5. Sync Diagnostics**
- [ ] Add diagnostics API: `/api/pwa/sync-diagnostics`
  - Last successful sync timestamp
  - Pending operations count
  - Failed operations count + reasons
  - Data size
  - Sync status
- [ ] Error classification: transient (retry) vs. permanent (user action needed)

### Frontend Enhancement

**7.6. Offline Indicator**
- [ ] Add header indicator: "Offline Mode" vs. "Online"
- [ ] Show sync status: "Synced" / "Syncing..." / "Pending Operations"
- [ ] Color indicator: green (synced), yellow (pending), red (errors)

**7.7. Draft Management UI**
- [ ] Auto-save drafts to local storage while typing
- [ ] Show draft list in app (where applicable)
- [ ] Add "Resume Draft" option
- [ ] Add "Discard Draft" option
- [ ] Show draft age ("Created 3 hours ago")

**7.8. Offline Queue UI**
- [ ] Show queued operations counts in app sidebar/footer
- [ ] Add "Pending Operations" view
  - List: operation description, created time, retry count, status
  - Actions: retry, discard, view error
- [ ] Show retry schedule ("Next retry in 5 minutes")
- [ ] Show errors clearly ("Failed: Server returned 404")

**7.9. Conflict Resolution UI**
- [ ] Detect conflicts: local change + remote change to same entity
- [ ] Prompt user: "Both you and another user changed this. Which version?"
  - Local version (your changes)
  - Remote version (their changes)
  - Merge (if possible)
- [ ] Simple merge strategy: per-field resolution

**7.10. Sync Retry/Resume**
- [ ] Add "Retry All Failed" button
- [ ] Add "Resume Sync" button (if stuck)
- [ ] Show error details for failed operations
- [ ] Suggest user action: "Update profile to fix validation error"

### Field Scenario Support

**7.11. Supported Offline Scenarios**
- [ ] **Briefing/Safety Instruction Mark:**
  - Download briefing form
  - Mark "Acknowledged" or "Refused" offline
  - Queue submission
  - Sync when online
  
- [ ] **Incident Draft Registration:**
  - Create incident report draft offline
  - Fill out form fields
  - Attach photo (if mobile browser supports)
  - Submit/queue for approval
  - Sync when online
  
- [ ] **Checklist Draft Completion:**
  - Download checklist for offline work
  - Check items as completed
  - Add comments
  - Photo capture (where applicable)
  - Queue submission
  
- [ ] **Task/Comment Capture:**
  - Write comment/note on entity
  - Flag for follow-up
  - Queue when offline
  
- [ ] **Media/Photo Sync:**
  - Capture photo while offline
  - Reference in incident/checklist/comment
  - Queue photo for upload
  - Sync when online

**7.12. Testing Field Scenarios**
- [ ] Manual testing: each scenario works offline and syncs correctly online
- [ ] Test: concurrent modifications + conflict resolution
- [ ] Test: large offline queue (many pending operations)

**Effort:** 3–4 weeks

**Validation:** User can work offline, create drafts, queue operations, and sync reliably when online.

---

## Phase 8: Operational UX Hardening on Existing Pages

**Goal:** Make existing data-bound pages daily-usable. No rewrites; UX maturity only.

**Pages to Enhance:**
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
- Client portal operational pages

### Pattern: UX Hardening Checklist

For each page:

- [ ] **Next Actions:** What should the user do on this page?
  - Primary action (most common)
  - Secondary actions (bulk, advanced)
  - Quick links to related workflows
  
- [ ] **Blockers/Readiness Context:**
  - Show readiness score (if applicable)
  - Show blocking issues (if any)
  - Show "Fix Blocker" deep link
  
- [ ] **Empty States:**
  - "No items yet" → with call-to-action ("Create first item", "Sync from system X")
  - "No items matching filter" → with reset filter option
  
- [ ] **Bulk Actions:**
  - Add multi-select checkbox
  - Show bulk actions on selected items
  - Include "Select All" / "Deselect All"
  - Typical actions: approve, reject, export, delete, tag, bulk-edit
  
- [ ] **Deep Links:**
  - Every item links to detail view
  - Detail view links back to list
  - Add breadcrumb navigation
  
- [ ] **Reduce Visual Clutter:**
  - Hide less-important columns (make sortable/filterable)
  - Move advanced filters to collapsible "More Options"
  - Limit initial sort to most relevant columns
  
- [ ] **Advanced Controls to Secondary Menu:**
  - Move: export, archive, duplicate, etc. to "⋯" menu
  - Keep primary actions visible
  
- [ ] **Obvious Primary CTA:**
  - Use color/size to highlight primary action
  - Place in consistent location (top-left action row)
  - Label clearly ("Create", "Approve All", "Export", etc.)

### Page-Specific Work

**8.1. AdminPage**
- [ ] Add: provider health, tenant health, queue health sections
- [ ] Add: data quality summary widget
- [ ] Add: feature enablement overview
- [ ] Add: audit log quick view

**8.2. ContractorsPage**
- [ ] Add: readiness score for each contractor
- [ ] Add: blockers summary
- [ ] Add: bulk approve-contractors action
- [ ] Add: sync from external system link

**8.3. ReferencePage**
- [ ] Add: template resolution explanation
- [ ] Add: version history timeline
- [ ] Add: bulk upload/replace reference data
- [ ] Add: data quality checks

**8.4. SettingsPage**
- [ ] Add: role/permission breakdown for current user
- [ ] Add: workflow customization options (where applicable)
- [ ] Add: notification preferences
- [ ] Add: offline settings (sync frequency, cache size)

**8.5. ActivitiesPage**
- [ ] Add: timeline/event filtering
- [ ] Add: bulk export/archive actions
- [ ] Add: advanced search/filter

**8.6. MedicalPage**
- [ ] Add: medical checkup readiness (current/expired/due soon)
- [ ] Add: bulk actions (mark completed, reschedule, export)
- [ ] Add: deep link to employee detail

**8.7. FireSafetyPage**
- [ ] Add: compliance status by rule/NPA
- [ ] Add: blockers for non-compliant areas
- [ ] Add: bulk remediation actions
- [ ] Add: document links for each rule

**8.8. FireTrainingPage**
- [ ] Add: training completion status by employee role
- [ ] Add: due-soon vs. overdue breakdown
- [ ] Add: bulk enroll action
- [ ] Add: acknowledgement tracking

**8.9. FireInspectionsPage**
- [ ] Add: inspection readiness + blockers
- [ ] Add: bulk schedule action
- [ ] Add: import/sync from inspector system
- [ ] Add: findings summary

**8.10. InspectionChecklistsPage**
- [ ] Add: usage frequency by checklist
- [ ] Add: completion rate by checklist
- [ ] Add: version management
- [ ] Add: bulk deploy to sites

**8.11. InspectionPlansPage**
- [ ] Add: plan coverage by site/area
- [ ] Add: next inspections timeline
- [ ] Add: bulk schedule action
- [ ] Add: dependency map (which rules require which inspections)

**8.12. InspectionPrepPackagesPage**
- [ ] Add: readiness score for each package
- [ ] Add: required documents checklist
- [ ] Add: asset allocation
- [ ] Add: bulk export for field teams

**8.13. Client Portal Pages**
- [ ] Add: role-based task inbox section
- [ ] Add: recent documents + links
- [ ] Add: helpful quick links
- [ ] Add: status dashboard (compliance, training, inspections)

**Effort:** 4–6 weeks (parallel phases)

**Validation:** Each page follows UX pattern and supports daily operational workflows.

---

## Phase 9: Enterprise Admin / Governance / Diagnostics

**Goal:** Make admin console operationally useful for tenant/platform admins.

### Backend Implementation

**9.1. Tenant Health Dashboard API**
- [ ] Create `/api/admin/tenant-health` endpoint returning:
  - User count
  - Active sessions
  - API usage (requests/hour)
  - Data storage (size, growth rate)
  - Key metrics (documents, training, incidents, etc.)
  - Health score (0–100%)
  - Recent errors/warnings

**9.2. Outbox/Webhook Diagnostics**
- [ ] Create `/api/admin/outbox-diagnostics` endpoint returning:
  - Total events in outbox
  - By status: pending, sent, failed
  - Failed events: error, reason, last_retry, next_retry
  - Dead-letter queue size
  - Event delivery lag (p50, p95, p99)

**9.3. Integration Readiness**
- [ ] Create `/api/admin/integration-readiness` endpoint returning:
  - Each configured integration: name, status (ready|degraded|blocked)
  - Last check time
  - Errors/warnings
  - Capability flags
  - Configuration summary

**9.4. Provider Mode Diagnostics**
- [ ] Create `/api/admin/provider-mode` endpoint returning:
  - Current mode: internal, external, hybrid
  - Which providers are in which mode
  - Which features depend on each provider
  - Status of each provider: healthy | degraded | unavailable
  - Fallback behavior (what happens if provider fails?)

**9.5. Queue/Job Diagnostics**
- [ ] Create `/api/admin/job-diagnostics` endpoint returning:
  - Active jobs count
  - Queued jobs count
  - Failed jobs count (last 24h)
  - Slow jobs (> threshold)
  - Dead-letter queue
  - Job type breakdown

**9.6. Audit Overview**
- [ ] Create `/api/admin/audit-overview` endpoint returning:
  - Sensitive actions (last 100): user, action, object, timestamp
  - Audit trail by user (if requested)
  - Data export history
  - Failed operations (last 24h)

**9.7. Data Quality Overview**
- [ ] Create `/api/admin/data-quality-overview` endpoint returning:
  - Total violati
ons by type
  - Violations by entity type
  - Trends (violations over time)
  - Top blockers by frequency

**9.8. Billing/Usage Overview**
- [ ] Create `/api/admin/billing-overview` endpoint returning:
  - Current month usage
  - Charges (estimated or actual)
  - Usage by feature/module
  - Forecast (if applicable)

**9.9. Startup/Onboarding Diagnostics**
- [ ] Create `/api/admin/startup-readiness` endpoint returning:
  - Essential setup steps: completed | pending
    - Tenant configured?
    - Users imported?
    - Templates loaded?
    - Reference data synced?
    - Integrations configured?
    - Diagnostics OK?
  - Recommended next steps
  - Setup guide links

**9.10. Feature/Module Enablement**
- [ ] Create `/api/admin/feature-flags` endpoint returning:
  - Each feature: enabled | disabled | preview
  - Feature description
  - Dependencies
  - Known issues
- [ ] Implementation: decorator-based feature flags with admin UI

### Frontend Implementation

**9.11. Admin Dashboard**
- [ ] Create comprehensive admin landing page:
  - Tenant health summary widget
  - Alerts/warnings section
  - Queue health indicator
  - Recent errors/warnings
  - Quick links: data quality, integrations, audit, configuration
  - Setup progress (for new tenants)

**9.12. Tenant Health Page**
- [ ] Display all metrics from tenant-health API
- [ ] Show trends (charts over last 7/30 days)
- [ ] Show breakdown by feature (documents, training, incidents, etc.)

**9.13. Diagnostics Pages**
- [ ] Separate pages for:
  - Outbox/webhook diagnostics
  - Integration readiness
  - Provider mode status
  - Queue/job health
  - Audit overview
  - Data quality overview
  - Billing/usage
  - Feature enablement

**9.14. Admin Configuration UI**
- [ ] Create UI for:
  - Feature flag toggle
  - Provider selection/configuration
  - System settings
  - Integration API keys (with masking)
  - Sync/import configuration

**Effort:** 3–4 weeks (parallel phases)

**Validation:** Admin sees complete platform operational picture and can diagnose issues.

---

## Phase 10: Reliability / Observability / Runbooks

**Goal:** Make platform operationally sustainable.

### Reliability Tasks

**10.1. Retry Consistency**
- [ ] Audit all background jobs for retry behavior
- [ ] Normalize: exponential backoff (1m, 5m, 15m, 1h, 4h)
- [ ] Normalize: max retries (3–5 typically)
- [ ] Implement: circuit breaker for cascading failures
- [ ] Test: retry behavior correctness

**10.2. Dead-Letter Queue (DLQ) / Poison Handling**
- [ ] Define: when does an operation go to DLQ? (> max retries typically)
- [ ] Implement: DLQ queue isolation
- [ ] Implement: DLQ monitoring + alerting
- [ ] Implement: manual retry from DLQ (admin action)
- [ ] Test: DLQ handling

**10.3. Heartbeat / Watchdog**
- [ ] Implement: periodic health check (every 1 min)
  - Database connectivity
  - Cache connectivity
  - Message queue connectivity
  - External integrations (if configured)
- [ ] Create: `/api/health` endpoint
- [ ] Alerting: health check failures

**10.4. Failed Job Diagnostics**
- [ ] For each failed background job, capture:
  - Error type + stack trace
  - Correlation id + context
  - Input parameters
  - Retry count + history
- [ ] API: `/api/admin/failed-jobs?limit=...&type=...`
- [ ] Implement: log export for diagnostics

**10.5. Cleanup & Integrity Checks**
- [ ] Periodic cleanup jobs:
  - Expired sessions
  - Orphaned drafts (> 30 days old)
  - Completed jobs (archive old jobs)
  - DLQ entries (> 90 days)
- [ ] Periodic integrity checks:
  - Orphaned outbox events
  - Tenant isolation enforcement
  - Permission consistency
- [ ] Runbook: how to recover from data corruption

**10.6. Health/Readiness Endpoint Coverage**
- [ ] Ensure all critical paths have health checks:
  - Database migrations
  - Cache initialization
  - External provider connectivity (if configured)
  - Message queue connectivity
  - Required configuration validation
- [ ] API: `/api/readiness` (can this instance accept traffic?)

### Observability Tasks

**10.7. Logging Standards**
- [ ] Structured logging format (JSON)
- [ ] Include: timestamp, level, message, correlation_id, context, user, tenant
- [ ] Log levels: DEBUG, INFO, WARNING, ERROR
- [ ] Enforce: no sensitive data in logs (PII, API keys, etc.)

**10.8. Correlation ID Propagation** (continuation from Phase 2)
- [ ] Verify: correlation_id propagates through:
  - HTTP requests → background jobs
  - Background jobs → related jobs
  - All logging

**10.9. Metrics Collection**
- [ ] Collect: request latency (p50, p95, p99)
- [ ] Collect: error rates by endpoint
- [ ] Collect: job execution times + success rates
- [ ] Collect: database query performance
- [ ] Export: Prometheus/StatsD format

**10.10. Alerting Strategy**
- [ ] Define alerts:
  - High error rate (> 5% for 5 min)
  - High latency (p95 > threshold)
  - Failed job queue growing
  - Health check failing
  - Disk space low
- [ ] Implementation: alerting tool of choice (PagerDuty, Opsgenie, etc.)

### Runbooks

**10.11. Operational Runbooks**
Create documentation in `docs/OPERATIONAL_RUNBOOKS.md`:

- [ ] **Startup Checklist:** steps to boot platform fresh
- [ ] **Health Check:** how to verify platform is operational
- [ ] **Common Issues:**
  - "Integrations failing" → diagnostics steps
  - "Approval chain stuck" → recovery steps
  - "Offline sync not working" → troubleshooting
  - "Performance degrading" → investigation steps
- [ ] **Manual Interventions:**
  - How to clear failed job queue
  - How to rerun failed document process
  - How to recover corrupted entity
  - How to reset user session
- [ ] **Escalation:** when to escalate vs. auto-recover

**10.12. Local Bootstrap Reproducibility**
- [ ] Ensure: `docker-compose up` + `make bootstrap` brings up complete dev environment
- [ ] Ensure: seed data is reproducible
- [ ] Ensure: tests can run locally against this environment
- [ ] Document: bootstrap process in `docs/LOCAL_DEVELOPMENT.md`

**10.13. CI Verification Path**
- [ ] Ensure: CI runs all critical tests
- [ ] Ensure: CI validates consistency checks
- [ ] Ensure: CI checks for regressions on operational pages
- [ ] Document: CI pipeline in `docs/CI_PIPELINE.md`

**Effort:** 2–3 weeks

**Validation:** Platform can be debugged, recovered, and monitored using runbooks.

---

## Phase 11: Tests

**Goal:** Ensure all hardened/new code is verified.

### By Layer

**Backend Unit Tests**
- [ ] Tenant context enforcement
- [ ] Permission check correctness (read, write, bulk, export, search)
- [ ] Correlation ID propagation
- [ ] Audit logging for sensitive actions
- [ ] Error format consistency
- [ ] Readiness score calculation
- [ ] Blocker detection
- [ ] Data quality rules
- [ ] Retry/DLQ logic
- [ ] Provider mode diagnostics

**Backend Integration Tests**
- [ ] Tenant isolation verification (tenant A cannot see/modify tenant B data)
- [ ] Document lifecycle (template → ready → approve → sign → archive)
- [ ] Approval chain orchestration
- [ ] EDO workflow (if implemented)
- [ ] Background job execution + retry
- [ ] Offline sync correctness
- [ ] Role workspace projections
- [ ] Task inbox accuracy
- [ ] Outbox/webhook delivery

**Frontend Tests**
- [ ] Route permission enforcement (forbidden routes redirect)
- [ ] Action visibility (forbidden actions hidden, not just disabled)
- [ ] Loading/error/empty states render correctly
- [ ] Unsaved changes protection (warn on navigation)
- [ ] Form validation + error display
- [ ] Bulk actions function correctly
- [ ] Offline mode indicators
- [ ] Sync progress display
- [ ] Conflict resolution UI
- [ ] Page UX patterns (next actions, blockers, empty states, bulk UX)

**Contract Tests** (if applicable)
- [ ] Request/response format consistency
- [ ] Permission checks don't break integration
- [ ] Correlation ID passed through correctly
- [ ] Error format matches expectations

**End-to-End Tests**
- [ ] Complete document workflow: create → ready → approve → sign → archive
- [ ] Complete training workflow: define → assign → complete → acknowledge
- [ ] Complete offline workflow: go offline → create draft → sync when online
- [ ] Complete role workflow: user logs in → sees tasks → completes task → task removed

### Coverage Targets

| Layer | Current | Target |
|-------|---------|--------|
| Tenant isolation | ? | > 90% |
| Authz (read/write/bulk) | ? | > 90% |
| Document lifecycle | ? | > 85% |
| Readiness/blockers | 0% | > 90% |
| Tasks/workspace | 0% | > 80% |
| Workflows/approval/EDO | ? | > 80% |
| Offline sync | ? | > 85% |
| Operational pages | ? | > 70% |

**Effort:** 3–4 weeks (ongoing during phases, final polish here)

**Validation:** Coverage targets met, all critical paths tested.

---

## Deliverables by Phase

### After Each Phase

Update running documents:
- `docs/ENTERPRISE_USABILITY_COMPLETION_REPORT.md` — what's been completed
- `docs/ENTERPRISE_USABILITY_REMAINING_GAPS.md` — what's left
- `docs/ENTERPRISE_USABILITY_NEXT_STEPS.md` — recommended priorities

### Final Deliverables (After Phase 11)

**Documentation:**
- ✅ `docs/ENTERPRISE_USABILITY_AUDIT.md` — baseline facts
- ✅ `docs/ENTERPRISE_USABILITY_PLAN.md` — this plan (11 phases)
- ✅ `docs/ENTERPRISE_USABILITY_COMPLETION_REPORT.md` — what was delivered
- ✅ `docs/ENTERPRISE_USABILITY_REMAINING_GAPS.md` — obstacles + workarounds
- ✅ `docs/ENTERPRISE_USABILITY_NEXT_STEPS.md` — recommendations for next wave
- ✅ `docs/PLATFORM_CONSISTENCY_CHECKLIST.md` — consistency verification list
- ✅ `docs/DOCUMENT_LIFECYCLE_UNIFIED.md` — unified lifecycle spec
- ✅ `docs/TEMPLATE_RESOLUTION_HIERARCHY.md` — template priority rules
- ✅ `docs/PROVIDER_MODE_CAPABILITIES.md` — provider mode definitions
- ✅ `docs/INTERNAL_FALLBACK_PATTERNS.md` — non-production code paths
- ✅ `docs/DATA_QUALITY_RULES.md` — data quality check definitions
- ✅ `docs/OPERATIONAL_RUNBOOKS.md` — troubleshooting + recovery
- ✅ `docs/LOCAL_DEVELOPMENT.md` — bootstrap process
- ✅ `docs/CI_PIPELINE.md` — CI verification path

**Code:**
- ✅ All tenant/authz/audit consistency improvements
- ✅ Role workspaces + tasks + attention + blockers
- ✅ Document lifecycle unification
- ✅ Non-production fallback paths isolated/replaced
- ✅ Data quality rules + readiness + blockers
- ✅ PWA/offline hardening
- ✅ Operational page UX maturity
- ✅ Admin diagnostics + governance
- ✅ Reliability improvements (retries, DLQ, watchdog, etc.)
- ✅ Comprehensive tests

**Metrics:**
- ✅ Consistency pass: all endpoints/pages following pattern
- ✅ Coverage: > 90% tenant isolation, > 90% authz, > 85% document lifecycle
- ✅ Zero non-production code paths in production (all isolated/documented)
- ✅ All operational pages following UX pattern
- ✅ Admin can diagnose any operational issue

---

## Success Criteria

The platform is ready for corporate deployment when:

1. ✅ **Consistency:** Every endpoint behaves predictably (tenant context, permissions, errors, audit, correlation ID)
2. ✅ **Visibility:** User knows immediately what's urgent/blocked/due (task inbox, blockers, workspace)
3. ✅ **Document Core:** Document flows reliably from template → archive with full audit trail
4. ✅ **No Corporate Blockers:** All non-production fallback paths isolated/documented
5. ✅ **Data Quality:** Incomplete/expired/missing records detected and exposed
6. ✅ **Admin Capable:** Admins can see full operational picture and diagnose issues
7. ✅ **Offline Ready:** Users can work offline, sync reliably, resolve conflicts
8. ✅ **UX Mature:** Operational pages support daily workflows (bulk actions, next actions, blockers, deep links)
9. ✅ **Reliable:** Failures handled gracefully, retries work, recovery documented
10. ✅ **Tested:** Core paths verified, coverage targets met, no regressions

---

## Timeline Estimate

| Phase | Duration | Notes |
|-------|----------|-------|
| 1 — Audit | 1–2 weeks | ✅ Completed |
| 2 — Consistency | 3–4 weeks | Foundation for trust |
| 3 — Workspaces/tasks | 4–5 weeks | Key for daily use |
| 4 — Document core | 5–6 weeks | Parallel with Phase 3 |
| 5 — Fallback removal | 4–5 weeks | Entity blocker |
| 6 — Data quality | 3–4 weeks | Parallel with Phase 5 |
| 7 — PWA/offline | 3–4 weeks | Parallel phases |
| 8 — Page UX | 4–6 weeks | Parallel phases |
| 9 — Admin/governance | 3–4 weeks | Parallel phases |
| 10 — Reliability | 2–3 weeks | Ongoing thread |
| 11 — Tests | 3–4 weeks | Test coverage |
| **Total** | **~8–12 weeks** | Intensive full-time |

**Parallelization:** Phases 3–10 have significant parallel work possible.

---

## Resource Requirements

- **1 senior full-stack engineer** (lead): all phases
- **1 backend engineer** (optional): phases 2, 4, 5, 6, 10, 11
- **1 frontend engineer** (optional): phases 3, 8, 9, 11
- **1 QA engineer** (optional): phase 11, ongoing test coverage

**Recommendation:** Start with 1 lead; add backend/frontend engineers if timeline is critical.

---

## Next Steps (For Codex)

1. ✅ Accept this mission
2. ✅ Validate current state against **ENTERPRISE_USABILITY_AUDIT.md**
3. ✅ Proceed with Phase 2 (consistency hardening)
4. ✅ Update living documents weekly
5. ✅ Verify success criteria after each phase
6. ✅ Adjust timeline based on actual findings

---

**Last Updated:** March 24, 2026  
**Status:** Ready for Codex execution
