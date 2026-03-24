# Phase 2: Consistency Hardening — Detailed Audit
**Date:** March 24, 2026  
**Status:** BASELINE FINDINGS (Pre-hardening)

---

## Overview

This document captures the **baseline state of consistency issues** before Phase 2 begins. It serves as a verification checklist during hardening work.

---

## 1. Tenant Context Enforcement

### Finding 1.1: Tenant Context Extraction ✅
**Status:** PARTIALLY IMPLEMENTED  
**Files:** `backend/app/api/dependencies.py`, `backend/app/middleware/tenant.py`

**Current Pattern:**
- ✅ All routes have `get_tenant_record` dependency (extracts from header or preloaded state)
- ✅ Tenant context stored in `request.state.tenant_record` and `request.state.tenant_id`
- ✅ Session augmented with `info["tenant"]` and `info["tenant_id"]`
- ✅ Fallback tenants defined for auth/portal/webhooks

**Issues Found:**
- ⚠️ `_resolve_fallback_tenants()` allows routes to operate without explicit tenant header (auth, portal, webhooks)
  - Lines 40–54 in dependencies.py
  - Risk: Some paths may skip tenant validation when fallback is used
- ⚠️ Some routes may not validate tenant in request.state uniformly
  - Need to audit each route handler

**Phase 2 Task:** Verify every route validates/uses tenant context; audit fallback usage.

---

### Finding 1.2: Background Jobs Tenant Context ⚠️
**Status:** INCONSISTENT  
**Files:** `backend/app/tasks.py`, `backend/app/celery/tasks/*`

**Current Pattern:**
- Celery tasks referenced in task.py line 206: `correlation_id = str(metadata.get("correlation_id") or run.id)`
- Jobs store tenant in metadata

**Issues Found:**
- ⚠️ Not all background jobs preserve tenant context from originating request
- ⚠️ Job status reporting may lose tenant context on retry/requeue
- ⚠️ No audit decorator on Celery task execution

**Phase 2 Task:** Create background job tenant context wrapper; audit all Celery tasks.

---

## 2. Permission Checks

### Finding 2.1: ABAC/RBAC Usage ⚠️
**Status:** MIXED PATTERNS

**Files:** 
- training.py: Uses `abac(_tenant_resource_id, required_roles=_TRAINING_READ_ROLES)`
- ppe.py: Uses `abac(_tenant_resource_id, required_roles=_PPE_READ_ROLES)`
- attestations.py: Uses `abac()`
- npa.py: Uses `rbac`
- notifications.py: Uses `rbac`
- risk_enterprise.py: Uses `rbac`
- outbox_admin.py: Uses `rbac`
- briefings.py: Uses `rbac`

**Issues Found:**
- ⚠️ Some routes use ABAC, some use RBAC (inconsistent)
- ⚠️ Permission check patterns vary by file
- ⚠️ No unified permission check helper
- ⚠️ Some routes lack permission checks entirely (need audit)

**Phase 2 Task:** Standardize on single permission pattern; create helper library.

---

### Finding 2.2: Permission Error Formatting ⚠️
**Status:** INCONSISTENT

**Current HttpException Usage:**
```python
# Pattern A (some routes):
HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

# Pattern B (training.py):
HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "...", "message": "..."})

# Pattern C (various):
HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
```

**Issues Found:**
- ⚠️ No standardized error envelope across endpoints
- ⚠️ Some errors include `code` field, some don't
- ⚠️ Some return structured detail, some return plain strings
- ⚠️ Permission denied errors not consistently identified

**Phase 2 Task:** Create standardized error envelope; use across all endpoints.

---

## 3. Error Response Format

### Finding 3.1: Error Envelope Inconsistency 🔴
**Status:** NOT STANDARDIZED

**Examples Found:**
- training.py line 70: `{"code": "training_validation_error", "message": message}`
- middleware/tenant.py line 65: `{"error_Code": "...", "message": "...", "correlation_id": "..."}`
- Various routes: Plain string messages

**Issues Found:**
- ⚠️ No shared error response schema
- ⚠️ Sometimes `code`, sometimes `error_code`, sometimes missing
- ⚠️ Sometimes `message`, sometimes `detail`
- ⚠️ Correlation ID only in middleware errors, not endpoint errors

**Phase 2 Task:** Create global error middleware; standardize all error responses.

---

### Finding 3.2: Middleware Error Handling ✅
**Status:** PARTIALLY IMPLEMENTED

**Files:** `backend/app/middleware/tenant.py` (lines 58–70)

**Current Pattern:**
```python
def _error(status_code: int, correlation_id: str, *, code: str, message: str, err_type: str = "tenancy") -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_Code": code,  # Note: inconsistent capitalization
            "message": message,
            "correlation_id": correlation_id,
            "type": err_type,
        },
    )
```

**Issues Found:**
- ⚠️ Global error format defined, but only in tenant middleware (not applied everywhere)
- ✅ Includes correlation_id
- ⚠️ Capitalization inconsistent: `error_Code` vs. `code`

**Phase 2 Task:** Apply tenant middleware error pattern globally; fix capitalization.

---

## 4. Correlation ID Propagation

### Finding 4.1: Middleware Extraction ✅
**Status:** IMPLEMENTED

**Files:** `backend/app/middleware/tenant.py` (lines 85–86)
**Code:**
```python
correlation_id = get_trace_id(request, get_settings().trace_header_name)
request.state.correlation_id = correlation_id
```

**Issues Found:**
- ✅ Extracted at middleware level
- ✅ Stored in request.state
- ✅ Returned in response header (line 212): `response.headers["X-Correlation-Id"] = correlation_id`
- ⚠️ BUT: Not returned in error responses automatically

**Phase 2 Task:** Ensure correlation_id in all error responses; propagate to endpoints.

---

### Finding 4.2: Background Job Propagation ⚠️
**Status:** PARTIAL

**Files:** `backend/app/tasks.py` (line 206)
**Code:**
```python
correlation_id = str(metadata.get("correlation_id") or run.id)
```

**Issues Found:**
- ⚠️ Correlation ID for background jobs extracted from metadata, but:
  - Not guaranteed to be set when job is enqueued
  - No middleware/decorator to auto-inject when job starts
  - No correlation ID log context across job execution

**Phase 2 Task:** Add correlation ID auto-injection for all Celery tasks.

---

### Finding 4.3: Service Layer & Logging ⚠️
**Status:** INCOMPLETE

**Issues Found:**
- ⚠️ Service layer functions (backend/app/services/*.py) don't receive correlation_id
- ⚠️ Logging doesn't include correlation_id in all log statements
- ⚠️ No log context/middleware to auto-inject correlation_id into logs

**Phase 2 Task:** Add correlation ID to logging context; propagate through service layer.

---

## 5. Audit Logging

### Finding 5.1: Audit Decorator ⚠️
**Status:** PARTIALLY IMPLEMENTED

**Files:** `backend/app/core/audit_decorator.py` (referenced in tenants.py line 2)

**Current Usage:**
- tenants.py line 18: `@audit_operation("create", "tenant")`

**Issues Found:**
- ⚠️ Only some endpoints use audit decorator
- ⚠️ Not all sensitive operations audited:
  - ❌ Approval/sign operations?
  - ❌ Document operations?
  - ❌ Bulk operations?
  - ❌ Data export?
  - ❌ Permission changes?

**Phase 2 Task:** Audit all endpoints; add audit_operation to sensitive actions.

---

### Finding 5.2: Audit Decorator Content ⚠️
**Status:** UNKNOWN (need to inspect)

**Phase 2 Task:** Verify audit decorator includes:
- ✅ User (from token)
- ✅ Tenant
- ✅ Action (operation)
- ✅ Object (entity)
- ✅ Timestamp
- ✅ Correlation_id
- ✅ Changes (before/after, if mutation)

---

## 6. Frontend Route-Level Permissions

### Finding 6.1: Route Permission Checks ⚠️
**Status:** INCOMPLETE

**Files:** `frontend/router.ts` (or similar router definition)

**Issues Found:**
- ⚠️ Frontend routes may not check permissions before rendering
- ⚠️ Forbidden routes might be visible (should redirect)
- ⚠️ Permission matrix not enforced at route level

**Phase 2 Task:** Audit all routes; add permission check guard.

---

## 7. Frontend Action-Level Permissions

### Finding 7.1: Button/Action Visibility ⚠️
**Status:** INCOMPLETE

**Issues Found:**
- ⚠️ Not all forbidden actions hidden (some just disabled)
- ⚠️ No visual indication why action is disabled
- ⚠️ No consistent pattern for showing permission-denied feedback

**Phase 2 Task:** Audit operational pages; hide forbidden actions + show reason.

---

## 8. Frontend Loading/Error/Empty States

### Finding 8.1: State Consistency ⚠️
**Status:** INCONSISTENT

**Issues Found:**
- ⚠️ Not all data-fetching pages have loading state
- ⚠️ Error states vary (some show nothing, some show generic error)
- ⚠️ Empty states missing or inconsistent

**Phase 2 Task:** Create standard state components; apply to all pages.

---

## 9. Unsaved Changes Protection

### Finding 9.1: Form Protection ⚠️
**Status:** INCOMPLETE

**Issues Found:**
- ⚠️ Not all forms warn on unsaved changes
- ⚠️ Critical forms (approval, signing) may allow accidental loss of data

**Phase 2 Task:** Identify critical forms; add dirty-flag tracking + warn on navigate.

---

## Summary of Consistency Gaps

### High Priority (Must Fix for Reliability)
| Category | Gap | Impact | Files |
|----------|-----|--------|-------|
| Tenant Context | Background jobs may lose tenant | Data isolation risk | tasks.py, celery/* |
| Permission Checks | Mix of ABAC/RBAC patterns | Unpredictable behavior | Multiple routes |
| Error Formats | Inconsistent error envelopes | Client confusion | All routes |
| Correlation ID | Missing from some paths | Cannot trace requests | Service layer, logs |
| Audit Logging | Incomplete coverage | Compliance gap | Multiple routes |

### Medium Priority (Important for UX/Ops)
| Category | Gap | Impact | Files |
|----------|-----|--------|-------|
| Frontend Perms | Route checks incomplete | UX leak (forbidden routes visible) | frontend/* |
| Loading States | Inconsistent | Confusing UX | frontend pages |
| Error Messages | Varied formatting | Unclear to users | All endpoints |

### Low Priority (Polish)
| Category | Gap | Impact | Files |
|----------|-----|--------|-------|
| Unsaved Changes | Critical forms may not warn | User data loss | frontend forms |

---

## Phase 2 Execution Roadmap

### Week 1: Foundation (Tenant + Correlation)
- [ ] Audit all routes for tenant context usage
- [ ] Verify background jobs preserve tenant
- [ ] Add correlation ID to service layer
- [ ] Add correlation ID to logging context

### Week 1–2: Permission Standardization
- [ ] Create unified permission check helper
- [ ] Standardize on single ABAC or RBAC pattern
- [ ] Apply to all routes
- [ ] Audit missing permission checks

### Week 2: Error Standardization
- [ ] Define global error envelope schema
- [ ] Create error builder middleware
- [ ] Apply to all endpoints
- [ ] Ensure correlation_id in all errors

### Week 2–3: Audit Logging
- [ ] Identify all sensitive operations
- [ ] Add audit_operation decorator to each
- [ ] Verify audit content (user, tenant, change, correlation_id)

### Week 3: Frontend Permission & State
- [ ] Add route-level permission checks
- [ ] Hide forbidden actions (not just disable)
- [ ] Create standard state components (Loading, Error, Empty)
- [ ] Apply to operational pages

### Week 3–4: Forms & Validation
- [ ] Add unsaved changes warning to critical forms
- [ ] Test protection on various workflows

---

## Testing Strategy for Phase 2

### Unit Tests
- Tenant context in all routes
- Permission checks (allow/deny scenarios)
- Error envelope format

### Integration Tests
- Tenant isolation (Tenant A cannot see Tenant B data)
- Background jobs preserve tenant
- Correlation ID persists through request-job-response cycle
- Audit logging captures all sensitive operations

### E2E Tests
- Forbidden route redirects
- Forbidden action hidden
- Unsaved form warns on navigate
- Error message displays to user

---

## Gates Before Phase 3

Before Phase 3 starts, validate:

- [ ] All endpoints enforce tenant context
- [ ] All routes check permissions (no unprotected endpoints)
- [ ] All error responses follow standard envelope
- [ ] All sensitive operations audited
- [ ] Correlation ID propagates through all paths
- [ ] Frontend routes check permissions
- [ ] Frontend actions respect permissions
- [ ] State components consistent
- [ ] Critical forms protected

---

## Known Unknowns (Need Investigation)

1. **Is `audit_decorator` fully implemented?** Need to check `backend/app/core/audit_decorator.py`
2. **Which background jobs exist?** Need to audit `backend/app/celery/tasks/*`
3. **Which routes lack permission checks?** Need full route audit
4. **Are there any unprotected endpoints?** Need security scan

---

**Status:** READY FOR PHASE 2 EXECUTION

**Next Action:** Start with Week 1 tasks (tenant context audit + correlation ID propagation)
