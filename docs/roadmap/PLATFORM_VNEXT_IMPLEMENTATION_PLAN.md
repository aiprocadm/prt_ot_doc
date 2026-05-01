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

