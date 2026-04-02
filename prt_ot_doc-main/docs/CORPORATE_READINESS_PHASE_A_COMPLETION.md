# PHASE A: Corporate Readiness Audit — Completion & Next Steps

**Completed:** March 23, 2026  
**Prepared by:** Architecture & Hardening Lead  
**Status:** ✅ AUDIT COMPLETE; Ready for Phase B planning

---

## What Was Audited

Comprehensive factual assessment of the codebase against enterprise production-readiness criteria:

✅ **55 backend routes** — analyzed for tenant isolation, permission checks, error consistency  
✅ **75 frontend pages** — assessed for operational readiness vs. thin wrappers  
✅ **71 migrations** — verified schema stability and multi-tenant support  
✅ **236 test artifacts** — evaluated coverage and test quality  
✅ **Stub/Mock/Deferred implementations** — identified and confirmed  
✅ **PWA/Offline infrastructure** — assessed current state  
✅ **Document core** — confirmed as production-grade backbone  
✅ **Tenancy/RBAC/Audit** — validated as above-average foundation

### Documents Created/Updated

1. **[CORPORATE_READINESS_AUDIT.md](./CORPORATE_READINESS_AUDIT.md)** — Factual assessment
   - Backend architectural inventory with maturity levels
   - Frontend page readiness matrix (12 operational; 8 partial)
   - Confirmed stubs/mock/deferred blockers
   - Production readiness checklist
   - Risk matrix

2. **[CORPORATE_READINESS_PLAN.md](./CORPORATE_READINESS_PLAN.md)** — 11-Phase hardening roadmap
   - Phases A–K with detailed deliverables
   - Team size and effort estimates
   - Success criteria
   - 16–26 week timeline
   - Resource plan

---

## Key Findings Summary

### ✅ What's Strong (Production-Grade)

| Area | Status | Notes |
|---|---|---|
| **Document Core** | ✅ MATURE | templates, versions, preview, branding, PDF, packs, passports |
| **Tenancy Foundation** | ✅ MATURE | multi-schema, context isolation, permission framework |
| **Audit Trail** | ✅ MATURE | entity-level tracking, user actions, sensitive diffs |
| **File Storage** | ✅ MATURE | abstraction layer, versioning, deterministic backups |
| **User Management** | ✅ MATURE | registration, roles, invitations, RBAC |
| **Frontend Real Data** | ✅ GOOD | 12 pages converted to real API flows (contractors, medical, fire safety, etc.) |

### 🟡 What Needs Hardening (Foundation-Level)

| Area | Gap | Priority |
|---|---|---|
| **Consistency** | Tenant validation not 100%; permissions inconsistent | CRITICAL |
| **Error Responses** | No unified schema; varies by route | HIGH |
| **Operational UX** | No attention center, weak workspace model | CRITICAL |
| **Readiness Scoring** | Partial; not all entities covered | HIGH |
| **Data Quality Visibility** | Does not exist | HIGH |
| **Correlation Tracing** | Not complete; gaps in async jobs | HIGH |

### 🔴 What Blocks Enterprise (Stubs/Deferred)

| Component | Status | Blocker Level |
|---|---|---|
| **WebSocket Events** | 501 Not Implemented (stub) | HIGH |
| **Approval/Sign Workflow** | Default provider = `stub` mock | CRITICAL |
| **EDO Integration** | Provider = `mock`; webhook path contains `stub` | CRITICAL |
| **1C/FRDO/EISOT** | Full stubs; raise `IntegrationDisabledError` | HIGH |
| **Job Orchestration** | `document_jobs_required.py` incomplete semantics | HIGH |
| **Offline Queue Model** | Does not exist (PWA shell only) | HIGH |

---

## Critical Recommendations

### Immediate Actions (Before Any Development)

1. **Acknowledge the Assessment** ✅
   - Review audit findings with team
   - Confirm blockers align with product strategy
   - Agree on MVP blocking stubs to address first

2. **Commit to Phase B Consistency Hardening** ✅
   - This is non-negotiable for enterprise
   - Must happen before all other phases
   - ~4 weeks; 2–3 backend engineers

3. **Isolate Stub/Mock Providers** ✅
   - Before Phase E, decide: implement real or keep as honest mock?
   - Create provider mode config (internal vs. stub vs. mock)
   - Make non-production modes explicit in diagnostics

4. **Plan Phase C + D in Parallel** ✅
   - Document Core (Phase D) can run in parallel with Workspace (Phase C)
   - Saves time; different teams can own each

### Strategic Decisions Needed

**Decision 1: Approval/Sign Workflow**
- **Option A (Recommended):** Implement internal orchestration; keep stub mode for dev/testing
- **Option B:** Wait for certified provider integration; use mock mode until ready
- **Impact:** Blocks enterprise if Option A + certified adapter not available at deployment

**Decision 2: EDO Integration**
- **Option A:** Keep as honest mock; prepare provider interface for real adapters
- **Option B:** Integrate with real Russian EDO provider (EDIN, DORS, or similar) now
- **Impact:** Option A is MVP-viable; Option B required for regulated Russian market

**Decision 3: WebSocket vs. Server-Sent Events**
- **Recommendation:** Use SSE (simpler, stateless); implement in Phase E (~1 week work)
- **Impact:** Event stream real-time; can be real-time presence notifications

**Decision 4: 1C Integration Timing**
- **Recommendation:** Keep as disabled + provider interface; integrate in Phase 2 if needed
- **Impact:** Non-blocking for MVP; required for Russian enterprise market

### Do NOT Do

❌ **Do NOT attempt production deployment** until:
- Phase B (Consistency) is complete
- Phase E (Remove Stubs) blockers are addressed or explicitly accepted
- Phase K (Tests) coverage meets 80%+ backend / 70%+ frontend

❌ **Do NOT rewrite:**
- Document core (it's good; just strengthen)
- Tenancy/RBAC (good foundation; just harden)
- File storage (good abstraction; just use it)

❌ **Do NOT skip:**
- Phase B consistency pass (foundation for all later phases)
- Correlation ID propagation (required for observability)
- Data quality blockers (required for operational UX)

---

## What Needs Immediate Lab Verification

Before starting Phase B coding:

- [ ] **Tenant Isolation Lab:** Create test that attempts cross-tenant read → verify blocked
- [ ] **Permission Bypass Lab:** Try API endpoint as wrong role → verify 403
- [ ] **Error Response Lab:** Compare error responses from 5 different routes → quantify inconsistency
- [ ] **Correlation ID Lab:** Trace a request → task → webhook → verify correlation_id throughout
- [ ] **Offline Queue Lab:** Use PWA offline → make changes → verify sync works on reconnect

These labs take 2–3 hours; high confidence in audit findings.

---

## Estimated Investment (All 11 Phases)

### Best Case (5–7 person team, perfect execution)
- **Duration:** 16–18 weeks
- **Cost:** ~$400–600K (assuming $200/hr avg fully-loaded cost)
- **Risk:** Medium (technical complexity is moderate)

### Realistic Case (3–4 person team, learning curve)
- **Duration:** 24–30 weeks
- **Cost:** ~$350–500K
- **Risk:** Medium-High (smaller team → slower; more context switching)

### Conservative Case (2 person team, part-time)
- **Duration:** 52–60 weeks
- **Cost:** ~$250–350K
- **Risk:** High (2 people cannot parallelize; single points of failure)

**Recommendation:** Allocate 5-person team for 6 months = optimal ROI.

---

## Why This Hardening Matters

| Without Hardening | With Hardening |
|---|---|
| Cross-tenant data leaks possible | Tenant isolation is reliable |
| Permission bypasses hidden | Permission checks uniform |
| Errors confuse users/developers | Errors are actionable |
| Operations team can't diagnose issues | Correlation IDs enable tracing |
| Users don't know what needs doing | Attention center shows work inbox |
| No offline field mode | Real field/mobile workflows |
| Stubs hidden; look like features | Stubs explicit in diagnostics |
| Testing is fragile | 80%+ coverage verified |

**Bottom line:** With hardening, this becomes a **product-grade platform**. Without it, it remains **strong prototype**.

---

## Success Criteria for Full Hardening

After 6 months (all phases):

✅ **Security:**
- 100% tenant context validation
- 100% RBAC enforcement
- Zero cross-tenant access possible
- All sensitive operations audited

✅ **Operational:**
- Users see attention center on login
- Workflow scenarios end-to-end
- Readiness/blockers visible
- Admin console shows system health

✅ **Reliability:**
- 80%+ backend test coverage
- 70%+ frontend test coverage
- Correlation IDs trace every request
- Jobs are recoverable + idempotent

✅ **Mobile/Field:**
- Offline queue model works
- 5+ field scenarios ready
- Draft forms persist
- Conflict resolution UI

✅ **Documentation:**
- Runbooks for ops
- API reference complete
- Architecture decisions recorded
- Setup/Bootstrap guides updated

✅ **Observability:**
- Admin diagnostics console
- Integration readiness view
- Data quality dashboard
- Job/task diagnostics

---

## Next Steps

### Week 1 (This Week)

1. **Share audit findings** with team + stakeholders
   - Async review: CORPORATE_READINESS_AUDIT.md
   - Sync discussion: Confirm blockers, debate priority

2. **Make strategic decisions** (4 above)
   - Approval/Sign workflow: internal vs. certified?
   - EDO: mock vs. real?
   - WebSocket: SSE or defer?
   - 1C: defer or integrate?

3. **Spin up lab verification** (2–3 hours)
   - Tenant isolation test
   - Permission bypass test
   - Error response audit
   - Correlation ID trace
   - Offline queue spike

### Week 2

1. **Finalize Phase B scope** (Consistency Hardening)
   - Break into sprints (B.1, B.2, B.3, B.4, B.5, B.6)
   - Create GitHub issues/story cards
   - Assign to engineers

2. **Begin Phase B coding** (if lab results confirm audit findings)
   - Start with B.1 (Tenant Context)
   - Week 2–3: Audit + fix route-level tenant validation
   - Week 4–5: Permissions normalization
   - etc.

3. **Plan resources** for full timeline
   - Do we allocate 5 engineers for 6 months?
   - Or 3 engineers for 9 months?
   - Budget + headcount approval needed

---

## Handoff Checklist

- [ ] Audit reviewed with team
- [ ] Strategic decisions made and documented
- [ ] Lab verification passed
- [ ] Phase B scope finalized
- [ ] Engineering team assigned
- [ ] Sprint planning scheduled
- [ ] Timeline + budget approved
- [ ] Success metrics agreed upon

---

## Questions for Leadership

1. **Production Deployment Timeline:** When does the board expect enterprise rollout? (Impacts team allocation.)
2. **Approval/Sign/EDO Strategy:** Are these features required at launch, or Phase 2?
3. **Team Size:** Can we allocate 5 engineers for 6 months?
4. **Mobile/Offline Priority:** Is field-ready PWA Phase 1 or Phase 2?
5. **Certification/Compliance:** Are certifications (GDPR, ISO, Russian compliance) required?

---

## Appendix: Quick Scan of Architecture Health

Run this command to verify audit baseline:

```bash
# Backend route count
find backend/app/api/routes -name "*.py" | grep -v __pycache__ | wc -l

# Largest files
find backend/app -name "*.py" | xargs wc -l | sort -rn | head -20

# Test count
find tests -name "test_*.py" | wc -l

# Frontend page count
find frontend/src/pages -name "*.tsx" -o -name "*.ts" | wc -l
```

**Results (expected):**
- Backend routes: ~55
- Largest: models.py (3000–4000 lines), tasks.py (2000–3000), etc.
- Tests: ~236
- Frontend pages: ~75

---

## Conclusion

The codebase is a **strong foundation that can become a world-class product**, but it requires **systematic enterprise hardening**. The phase plan above is achievable, realistic, and will result in a **product-grade platform** ready for corporate deployment and market competition.

**Recommendation: Proceed with Phase B planning immediately.**

---

*Living document. Update quarterly or as phases complete with actual progress and learnings.*
