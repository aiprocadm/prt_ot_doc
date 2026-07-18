# Enterprise Usability Next Steps
**Version:** 1.0  
**Date:** March 24, 2026  
**Status:** Ready for Codex Execution

---

## Overview

The platform audit is complete. The **11-phase plan** is documented. The next step is **execution**.

This document outlines:
- ✅ What's ready to start immediately
- ✅ How to sequence work
- ✅ What to validate before proceeding to next phase
- ✅ Critical metrics to track

---

## Immediate Actions (This Week)

### 1. Confirm Execution Team & Timeline

**Decision Point:** Who owns each phase?

**Options:**
- **Option A:** 1 senior full-stack engineer (lead) driving all 11 phases; 8–12 weeks
- **Option B:** Lead + backend engineer + frontend engineer; 6–8 weeks
- **Option C:** Smaller iterative waves (2–3 months each)

**Recommendation:** Option B (lead + backend + frontend) for 8–10 weeks intensive work.

### 2. Kickoff & Alignment

- [ ] Review `ENTERPRISE_USABILITY_AUDIT.md` with team
- [ ] Review `ENTERPRISE_USABILITY_PLAN.md` with team
- [ ] Confirm hard rules (no rewrites, tenant-safe, audit-aware)
- [ ] Agree on success criteria
- [ ] Book development time / clear calendar

### 3. Establish Tracking Process

- [ ] Set up weekly sync (30 min, status + blockers)
- [ ] Agree on update cadence (daily standup? weekly PRs?)
- [ ] Designate: who updates completion report / remaining gaps?
- [ ] Prepare: GitHub project board or Jira board for Phase 2 tasks

---

## Phase 2 Start (This Week or Next)

### Phase 2: Platform Consistency Hardening

**Focus:** Make platform behavior uniform. This is the **trust foundation** for everything after.

**Duration:** 3–4 weeks  
**Effort:** 1 lead + 1 backend engineer  
**Deliverables:**
- Tenant context enforcement across backend
- Standardized permission checks
- Structured error responses
- Correlation ID propagation
- Audit logging for sensitive operations
- Frontend route + action permission awareness
- Consistent loading/error/empty states
- Unsaved changes protection

### Phase 2 Execution Plan

**Week 1: Design & Planning**
- [ ] Backend: Create tenant context extraction helper (single source of truth)
- [ ] Backend: Create permission checker helper library
- [ ] Backend: Define structured error envelope (error_code, message, field, details, correlation_id)
- [ ] Frontend: Define permission check pattern (role + permission matrix)
- [ ] Frontend: Define state component pattern (Loading, Error, Empty)
- [ ] Create consistency test suite skeleton
- [ ] Create code review checklist for consistency

**Week 1–2: Backend Consistency Hardening**
- [ ] Apply tenant context enforcement to all route handlers
  - Use middleware for extraction + injection
  - Audit queries for tenant filtering
  - Audit mutations for tenant validation
  - Decorate background jobs with tenant preservation
- [ ] Normalize permission checks
  - Audit all endpoints (read/write/bulk/export/search)
  - Extract permission logic to helper
  - Standardize forbidden response (HTTP 403 + error envelope)
  - Test permission correctness
- [ ] Implement structured error format
  - Create error builder helper
  - Replace ad-hoc error returns
  - Test error format consistency
- [ ] Correlation ID propagation
  - Generate ID for every request (middleware)
  - Pass to background jobs
  - Log in every entry
  - Return in error responses
  - Test correlation_id tracing

**Week 2–3: Audit Coverage + Frontend Consistency**
- [ ] Add audit logging for sensitive operations
  - Identify sensitive actions (approve, sign, delete, bulk update, etc.)
  - Add audit entry for each (user, tenant, action, object, changes, timestamp, correlation_id)
  - Create audit query API
  - Test audit logging
- [ ] Frontend: Route-level permission awareness
  - Extract permission requirements per route
  - Add route guard (check permission before render)
  - Redirect if forbidden
  - Test route permission enforcement
- [ ] Frontend: Action-level permission awareness
  - Audit every button/menu action
  - Check permission before enable
  - Hide forbidden actions (not just disable)
  - Test action visibility

**Week 3–4: Frontend States + Finalization**
- [ ] Frontend: Consistent loading/error/empty states
  - Create standard state components
  - Apply to all data-fetching pages
  - Test state rendering
- [ ] Frontend: Unsaved changes protection
  - Identify critical forms
  - Add dirty-flag tracking
  - Warn on navigation/close if unsaved
  - Test protection
- [ ] Comprehensive testing
  - Run consistency test suite (should have > 80% pass rate)
  - Fix regressions
  - Manual QA on key endpoints + pages
- [ ] Documentation
  - Update `ENTERPRISE_USABILITY_COMPLETION_REPORT.md`
  - Update `ENTERPRISE_USABILITY_REMAINING_GAPS.md`

### Success Criteria for Phase 2

- ✅ All backend endpoints enforce tenant context (verify with query audit)
- ✅ All permission checks follow consistent pattern (verify with code review)
- ✅ All error responses follow structured format (verify with automated test)
- ✅ Correlation ID propagates through all paths (verify with log inspection)
- ✅ Sensitive operations audited (verify with audit query)
- ✅ Frontend routes check permissions (verify with permission matrix test)
- ✅ Frontend actions respect permissions (verify with visibility test)
- ✅ State components used consistently (verify with component audit)
- ✅ Critical forms warn on unsaved (verify with manual test)

### Exit Gate for Phase 3

Before starting Phase 3, validate:
- [ ] All Phase 2 success criteria met
- [ ] No regressions in existing workflows
- [ ] Consistency test coverage > 80%
- [ ] Team agreement: "Platform behavior is now predictable"

---

## Phase 3–4 Parallel Setup (Week 3–4)

While Phase 2 finalizes, start scoping:

### Phase 3: Role Workspaces / Tasks / Attention / Blockers

**Start Week 3–4:** Scoping + design  
**Start Week 5:** Implementation (parallel with Phase 2 finalization)

**Preliminary Tasks:**
- [ ] Backend: Design role projection API (`/api/workspaces/{role}`)
- [ ] Backend: Define task inbox types (approve, sign, review, acknowledge, fill, complete)
- [ ] Backend: Design blocker types (data quality, permissions, external wait, system)
- [ ] Frontend: Design landing page layout (task inbox, blockers, recent items, recommendations, quick links)
- [ ] Define event propagation strategy (WebSocket vs. polling fallback)

### Phase 4: Document Core Unification

**Start Week 4:** Scoping + design  
**Start Week 5:** Implementation (parallel with Phase 3)

**Preliminary Tasks:**
- [ ] Design unified document lifecycle (state machine diagram)
- [ ] Document template resolution hierarchy (system < tenant < company < site)
- [ ] Design readiness score formula (components + weights)
- [ ] Design dependency map (NPA → template → document → route)
- [ ] Design render metadata persistence schema

---

## Parallel Synchronization (Weeks 5–12)

Phases 3–11 have significant parallelization:

### Recommended Parallel Tracks

**Track A: User-Facing Features (Phases 3, 8)**
- Lead coordinator: 1 frontend engineer
- Phase 3: Role workspaces, tasks, attention, blockers (weeks 5–9)
- Phase 8: Operational page UX hardening (weeks 6–11, parallelizable by page)

**Track B: Backend Architecture (Phases 4, 5)**
- Lead coordinator: 1 backend engineer
- Phase 4: Document lifecycle unification (weeks 5–10)
- Phase 5: Fallback/stub elimination (weeks 5–9)
- Phase 6: Data quality rules (weeks 8–11, can overlap phases 5 end)

**Track C: Operational Systems (Phases 7, 9, 10)**
- Lead coordinator: 1 senior engineer or lead
- Phase 7: PWA/offline hardening (weeks 7–10)
- Phase 9: Admin/governance (weeks 10–13, follows phases 5–6)
- Phase 10: Reliability/observability (ongoing, especially weeks 11–13)

**Track D: Quality Assurance (Phase 11)**
- Lead coordinator: 1 QA engineer (or backend engineer)
- Phase 11: Tests + coverage (weeks 12–15, but started earlier with each phase)

### Synchronization Points

| Week | Milestone | Decision |
|------|-----------|----------|
| Week 2 | Phase 2 mid-review | Are consistency goals on track? |
| Week 4 | Phase 2 complete | Gate: meet success criteria? |
| Week 4 | Phases 3–4 design done | Gate: designs approved? |
| Week 7 | Phases 3–4–5 mid-review | Any blockers between tracks? |
| Week 9 | Phases 3–5 complete | Gate: meet success criteria? |
| Week 11 | Phases 6–7–9 mid-review | Converging for Phase 11? |
| Week 13 | Phases 1–10 complete | Gate: all 10 complete? |
| Week 15 | Phase 11 complete | Gate: coverage targets met? |

---

## Week-by-Week Gantt (Indicative)

```
Week 1:  [Phase 2: Planning & Design    ]
Week 2:  [Phase 2: Backend Hardening   ]
Week 3:  [Phase 2: Audit + FE Hardening] [Phase 3–4: Scoping    ]
Week 4:  [Phase 2: FE States + Test    ] [Phase 3–4: Design    ]
Week 5:  [Phase 3: Workspaces/Tasks    ] [Phase 4: Lifecycle   ] [Phase 5: Fallback...
Week 6:  [Phase 3: Attention/Blockers  ] [Phase 4: Dependency  ] [Phase 5: Providers ] [Phase 8: Admin...
Week 7:  [Phase 3: Landing + Widgets   ] [Phase 4: Readiness   ] [Phase 5: Audit     ] [Phase 8: Pages
Week 8:  [Phase 3: Complete           ] [Phase 4: Complete    ] [Phase 6: Data QA   ] [Phase 7: PWA...
Week 9:  [Phase 8: UX Hardening cont  ] [Phase 6: Dashboard   ] [Phase 7: Offline...
Week 10: [Phase 8: Pages complete     ] [Phase 9: Diagnostics] [Phase 7: Complete
Week 11: [Phase 9: Admin Complete     ] [Phase 10: Reliability
Week 12: [Phase 11: Tests + Coverage  ]
Week 13: [Phase 11: Complete          ]
```

---

## Critical Success Factors

### 1. Hard Rules Enforcement

Do NOT:
- ❌ Rewrite working code
- ❌ Break existing workflows
- ❌ Drop test coverage
- ❌ Ship non-tenant-safe code
- ❌ Miss audit logging for sensitive actions
- ❌ Leave non-production paths undocumented

### 2. Weekly Documentation Updates

**Owner:** Lead or designated scribe

**Updates (every Friday):**
- `ENTERPRISE_USABILITY_COMPLETION_REPORT.md` — what shipped this week
- `ENTERPRISE_USABILITY_REMAINING_GAPS.md` — gaps closed, new gaps discovered
- `ENTERPRISE_USABILITY_NEXT_STEPS.md` — (this doc) adjusted priorities

### 3. Gate Reviews After Each Phase

**Before moving to next phase:**
- [ ] Success criteria verified (not estimated)
- [ ] No regressions in existing functions
- [ ] Code reviewed for consistency
- [ ] Test coverage > target
- [ ] Documentation updated
- [ ] Next phase scoping complete

### 4. Team Communication

**Sync Cadence:**
- Daily standup (15 min, 3 tracks report)
- Weekly phase sync (30 min, all tracks align)
- Weekly demo (Friday, 15 min, show working software)

**Blocker Escalation:**
- Blocker identified → reported in daily standup
- Blocker unresolved > 1 day → escalates to lead
- Blocker unresolved > 2 days → escalates to product/architecture

---

## Success Metrics to Track

### Velocity Metrics

| Metric | Frequency | Target |
|--------|-----------|--------|
| Phases completed on time | Weekly | 100% |
| Success criteria met per phase | Phase end | 100% |
| Regressions found (should be low) | Weekly | < 2 per week |
| Code review cycle time | Daily | < 24h approval |

### Quality Metrics

| Metric | Frequency | Target |
|--------|-----------|--------|
| Test coverage tenant isolation | Phase 2 end | > 90% |
| Test coverage authz | Phase 2 end | > 90% |
| Test coverage document lifecycle | Phase 4 end | > 85% |
| Test coverage readiness/blockers | Phase 6 end | > 90% |
| Test coverage workflows | Phase 5 end | > 80% |

### Operational Metrics

| Metric | Frequency | Target |
|--------|-----------|--------|
| Consistency violations found during Phase 2 | Weekly | Decrease trend |
| Non-production fallback paths documented | Phase 5 end | 100% |
| Operational pages following UX pattern | Phase 8 end | 100% |
| Admin can see tenant health | Phase 9 end | Yes |

---

## Decision Points

### D1: Core Team Size
**When:** This week  
**Decision Needed:** 1 engineer vs. 3 engineers vs. distributed across time?  
**Impact:** Determines timeline (8–12 weeks vs. 12–16 weeks)

### D2: Parallel Sequencing Approval
**When:** Week 3  
**Decision Needed:** Confirm 4-track parallel execution strategy?  
**Impact:** Determines sync overhead + coordination complexity

### D3: Phase 2 Exit Gate
**When:** Week 4  
**Decision Needed:** All success criteria met? Proceed to Phase 3–4?  
**Impact:** Blocks all downstream phases

### D4: Phase 5 Approach (Fallback Elimination)
**When:** Week 5  
**Decision Needed:** For each non-production path, real implementation or explicit fallback?  
**Impact:** Determines architecture for approval/sign/edo, integrations

### D5: Phase 11 Coverage Targets
**When:** Week 12  
**Decision Needed:** Are coverage targets sufficient for corporate deployment?  
**Impact:** Determines release readiness

---

## Risk Mitigation

### Risk: Phase Slippage

**Indicator:** Phase extends > 1 week past plan  
**Mitigation:** Identify blocker + reduce scope (move to next wave) vs. add resources  
**Owner:** Lead

### Risk: Regressions in Existing Functions

**Indicator:** Bug reports on previously working features  
**Mitigation:** Revert PR; investigate root cause; add regression test  
**Owner:** Affected engineer + lead

### Risk: Non-Production Paths Unclear (Phase 5)

**Indicator:** Cannot decide: real implementation or fallback?  
**Mitigation:** Document "capability preview" mode; proceed with isolation + explicit marking  
**Owner:** Architecture lead

### Risk: Coverage Targets Not Met (Phase 11)

**Indicator:** Coverage < 80% for critical paths  
**Mitigation:** Extend Phase 11; prioritize highest-risk paths  
**Owner:** QA lead

---

## Definition of Done (All Phases)

A phase is complete when:

1. ✅ **Code shipped** — PRs merged to main
2. ✅ **Tested** — All tests passing, coverage targets met
3. ✅ **Documented** — Changes recorded in docs/
4. ✅ **No regressions** — Existing features still work
5. ✅ **Success criteria verified** — Not estimated; actually validated
6. ✅ **Known gaps recorded** — If any, explicitly documented + planned for later phase
7. ✅ **Team agreement** — "Yes, we're done and confident"

---

## Post-Phase 11: Deployment & Validation

### Pre-Deployment Checklist

- [ ] All 11 phases complete + documented
- [ ] No open regressions
- [ ] Coverage targets met (tenant > 90%, authz > 90%, workflows > 85%)
- [ ] Consistency test suite passes 100%
- [ ] Admin diagnostics functional
- [ ] Operational pages tested
- [ ] Offline workflows tested
- [ ] Runbooks written + validated

### Deployment Strategy

1. **Staging Verification:** Deploy to staging; team walks through success criteria scenarios
2. **Canary Deployment:** Roll out to 10% of tenants; monitor for 24h
3. **Full Rollout:** If canary healthy, roll out to all tenants
4. **Post-Deployment Monitoring:** 48h closewatch for operational issues

### Soft Launch Windows

- **Week 14:** Staging deployment + team validation
- **Week 15:** Canary deployment (if team agrees)
- **Week 16:** Full deployment (if canary clean)

---

## Continuous Improvement (Post-Phases)

### Monthly Reviews (After Deployment)

- [ ] Track operational metrics (uptime, error rate, cycles)
- [ ] Collect tenant feedback (what's working, what's still hard)
- [ ] Identify technical debt from phases (any refactoring needed?)
- [ ] Plan next wave of hardening (e.g., mobile-specific UX, advanced workflows)

### Next Waves (Planned for Q2–Q3 2026)

- **Wave 2 (Q2 2026):** Mobile UX polish, advanced workflows, integration partnerships
- **Wave 3 (Q3 2026):** Performance optimization, data analytics, tenant white-labeling
- **Wave 4 (Q4 2026):** Marketplace/extensibility, enterprise support tier, advanced compliance

---

## Questions & Answers

### Q: What if a phase takes longer than planned?

**A:** Identify root cause (design flaw, complexity, resources). Options:
1. Extend the phase (+1–2 weeks if necessary)
2. Reduce scope (defer non-critical gaps to next wave)
3. Add resources (if available)

Choose based on blocker severity. Document the decision.

### Q: What if we find a major bug in already-shipped code?

**A:** Fix immediately (don't defer). Update timeline if necessary. Add regression test. Document in completion report.

### Q: What if a non-production path is too complex to replace?

**A:** Don't replace. Isolate + document + add explicit feature flag + add admin warning. Defer real implementation to next wave.

### Q: Can we skip any phase?

**A:** No. Each phase unblocks the next. For example:
- Phase 2 (consistency) is the foundation for all others
- Phase 3 (tasks/attention) unblocks user satisfaction
- Phase 5 (fallback removal) is mandatory for corporate trust

Skip none; adjust scope if timeline is critical.

### Q: What if we finish early?

**A:** Excellent. Spend extra time on:
1. Test coverage (add edge cases, stress tests)
2. Performance optimization (profile + optimize hotspots)
3. Documentation (improve runbooks, edge-case guides)
4. Hardening (security audit, accessibility audit)

---

## Approval & Sign-Off

**This plan is ready for Codex execution when:**

- [ ] Audit document reviewed + accepted
- [ ] Plan document reviewed + accepted
- [ ] Team size confirmed
- [ ] Timeline approved
- [ ] Hard rules understood + agreed
- [ ] Success criteria written down
- [ ] Tracking process established

**Approval Signatures:**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Lead Engineer | — | — | — |
| Product | — | — | — |
| Architecture | — | — | — |

---

## Related Documents

- `docs/ENTERPRISE_USABILITY_AUDIT.md` — Current state assessment
- `docs/ENTERPRISE_USABILITY_PLAN.md` — Detailed 11-phase plan
- `docs/ENTERPRISE_USABILITY_COMPLETION_REPORT.md` — Weekly progress tracking
- `docs/ENTERPRISE_USABILITY_REMAINING_GAPS.md` — Gap inventory

---

**Last Updated:** March 24, 2026  
**Status:** Ready for execution  
**Next Review:** After Phase 2 (approximately April 21, 2026)
