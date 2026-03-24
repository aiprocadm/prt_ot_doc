# Phase 2 Week 1 — Implementation Plan
**Status:** Foundation Layer (Complete)  
**Date:** March 24, 2026

---

## Week 1 Goals

1. ✅ **Foundation helpers created** — centralized error handling, tenant validation, permissions, correlation ID
2. ⏳ **Middleware registration** — integrate new middleware into FastAPI app
3. ⏳ **First endpoint migration** — apply new patterns to 1-2 critical routes as proof-of-concept
4. ⏳ **Tests for foundation** — verify error format, tenant context, permission checks

---

## Created Foundation Files

### 1. `backend/app/core/errors.py` ✅
**Purpose:** Standardized error response format  
**Includes:**
- `ErrorDetail` Pydantic model (error_code, message, field, details, correlation_id, timestamp)
- `ErrorBuilder` helper for fluent error construction
- `ERROR_CODES` dict mapping error codes → (HTTP status, message)
- `get_default_message()` and `get_status_code()` helpers

**Usage Example:**
```python
error = (
    ErrorBuilder()
    .with_code("PERMISSION_DENIED")
    .with_message("User cannot modify this resource")
    .with_correlation_id(correlation_id)
    .build()
)
# Returns ErrorDetail with all fields populated
```

### 2. `backend/app/core/tenant_validation.py` ✅
**Purpose:** Tenant context enforcement  
**Includes:**
- `TenantContextValidator` class with static methods
- `ensure_tenant_context()` — validates tenant not None and is_active
- `ensure_session_tenant()` — validates session scoped to correct tenant
- `build_tenant_error()` — builds error responses for tenant issues
- `validate_tenant_in_operation()` — validates tenant in business logic

**Usage Example:**
```python
# In a route handler:
TenantContextValidator.ensure_tenant_context(tenant)
TenantContextValidator.ensure_session_tenant(session, tenant.slug)
```

### 3. `backend/app/core/permission_checker.py` ✅
**Purpose:** Unified permission checking  
**Includes:**
- `PermissionAction` enum (READ, WRITE, DELETE, ADMIN, EXPORT, BULK)
- `PermissionChecker` class with static methods
- `check()` — single permission check
- `check_any()` — OR logic
- `check_all()` — AND logic
- `require_permission()` — callable pattern

**Usage Example:**
```python
# In a route handler:
PermissionChecker.check(
    user_can_delete,
    action="delete",
    resource="document",
    correlation_id=request.state.correlation_id
)
```

### 4. `backend/app/core/correlation_id.py` ✅
**Purpose:** Correlation ID context management  
**Includes:**
- `CorrelationIDManager` for context var management
- `CorrelationIDLogger` that auto-injects correlation_id into logs
- `get_logger()` factory function

**Usage Example:**
```python
# In middleware or request handler:
CorrelationIDManager.set(correlation_id)

# In any service:
logger = get_logger(__name__)
logger.info("Processing document", extra={"document_id": doc_id})
# Automatically includes correlation_id in log
```

### 5. `backend/app/middleware/global_error_handler.py` ✅
**Purpose:** Global exception catching and standardized error responses  
**Includes:**
- `GlobalErrorHandlerMiddleware` BaseHTTPMiddleware
- Catches: ValueError, PermissionError, Exception
- Returns standardized ErrorDetail for all exceptions
- Includes correlation_id in all error responses

**Usage Notes:**
- Should be first middleware (before other middlewares)
- Catches HTTPException from routes and standardizes format
- Logs all errors with correlation_id

---

## Next Steps (Week 1–2)

### Step 1: Register Middleware in Main App

**File:** `backend/app/main.py` or FastAPI app initialization

**Changes Needed:**
```python
from app.middleware.global_error_handler import GlobalErrorHandlerMiddleware

app = FastAPI()
app.add_middleware(GlobalErrorHandlerMiddleware)
# ... other middleware ...
```

**Why:** Global error handler must be registered FIRST (outermost middleware).

### Step 2: Create Convenience Dependencies

**File:** `backend/app/api/dependencies.py` (extend)

**New Dependencies:**
```python
async def get_correlation_id(request: Request) -> str:
    """Get current request correlation ID."""
    cid = request.state.correlation_id
    if not cid:
        cid = request.headers.get("x-correlation-id", "unknown")
    return cid

Corr IdDep = Annotated[str, Depends(get_correlation_id)]
```

**Why:** Easier to inject correlation_id into route handlers.

### Step 3: Migrate First Route — Proof of Concept

**Candidate:** `backend/app/api/routes/tenants.py` (already good structure)

**Before:**
```python
@router.get("", response_model=TenantPage)
async def list_tenants_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantPage:
    # Old error handling
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
```

**After:**
```python
from app.core.errors import ErrorBuilder
from app.core.tenant_validation import TenantContextValidator
from app.core.permission_checker import PermissionChecker

@router.get("", response_model=TenantPage)
async def list_tenants_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    correlation_id: str = Depends(get_correlation_id),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantPage:
    # Validate tenant context
    TenantContextValidator.ensure_tenant_context(tenant)
    TenantContextValidator.ensure_session_tenant(session, tenant.slug)
    
    # Check permissions
    can_list = True  # Your permission logic
    PermissionChecker.check(
        can_list,
        action="read",
        resource="tenants",
        correlation_id=correlation_id
    )

    items, total = await list_tenants(session, tenant.slug, limit=limit, offset=offset)
    return TenantPage(items=items, total=total)
```

### Step 4: Test Foundation Layer

**Create:** `backend/tests/unit/test_consistency_helpers.py`

**Tests Needed:**
```python
def test_error_builder_complete_error():
    """Test ErrorBuilder constructs valid ErrorDetail."""
    error = (
        ErrorBuilder()
        .with_code("TEST_ERROR")
        .with_message("Test message")
        .with_correlation_id("corr-123")
        .build()
    )
    assert error.error_code == "TEST_ERROR"
    assert error.correlation_id == "corr-123"

def test_permission_checker_denied():
    """Test PermissionChecker raises on denied."""
    with pytest.raises(HTTPException, match="403"):
        PermissionChecker.check(False, action="write", resource="doc")

def test_tenant_validator_inactive():
    """Test TenantContextValidator rejects inactive tenant."""
    tenant = Tenant(is_active=False)
    with pytest.raises(ValueError):
        TenantContextValidator.ensure_tenant_context(tenant)

def test_correlation_id_context():
    """Test CorrelationIDManager context var."""
    CorrelationIDManager.set("test-123")
    assert CorrelationIDManager.get() == "test-123"
    CorrelationIDManager.clear()
    assert CorrelationIDManager.get() is None
```

---

## Implementation Checklist

### Part 1: Foundation (✅ COMPLETE)
- ✅ Created `errors.py` with ErrorDetail + ErrorBuilder
- ✅ Created `tenant_validation.py` with TenantContextValidator
- ✅ Created `permission_checker.py` with PermissionChecker
- ✅ Created `correlation_id.py` with CorrelationIDManager
- ✅ Created `global_error_handler.py` with middleware

### Part 2: Integration (Week 1–2)
- [ ] Register GlobalErrorHandlerMiddleware in app.py
- [ ] Add correlation_id dependency in dependencies.py
- [ ] Create tests for foundation layer
- [ ] Migrate tenants.py as PoC
- [ ] Run tests to verify PoC works

### Part 3: Scale (Week 2)
- [ ] Migrate remaining routes to new error format
- [ ] Standardize permission checks across all routes
- [ ] Verify correlation_id propagates through logs
- [ ] Verify all endpoints follow tenant validation

---

## Success Criteria for Week 1–2

- ✅ Foundation layer created + integrated
- ✅ Global error handler catches all exceptions
- ✅ All error responses follow standard format (error_code, message, correlation_id)
- ✅ Tenant context enforced in all operations
- ✅ Permission checks standardized
- ✅ Correlation ID propagates through requests
- ✅ At least 1 route migrated as proof-of-concept
- ✅ Foundation tests passing

---

## Architecture Drawing

```
HTTP Request
    ↓
[GlobalErrorHandlerMiddleware] ← Set correlation_id in context
    ↓
[TenantMiddleware] ← Extract tenant
    ↓
Route Handler
    ├─ get_correlation_id() Dep ← Inject correlation_id
    ├─ Tenant Dep ← Inject tenant
    ├─ TenantContextValidator.ensure_*() ← Validate tenant
    ├─ PermissionChecker.check() ← Validate permission
    ├─ Service layer ← Logger includes correlation_id automatically
    └─ Return response
    ↓
[Response] + X-Correlation-Id header
    ↓
HTTP Response
```

---

## Files Modified/Created This Week

**Created:**
- `backend/app/core/errors.py` ✅
- `backend/app/core/tenant_validation.py` ✅
- `backend/app/core/permission_checker.py` ✅
- `backend/app/core/correlation_id.py` ✅
- `backend/app/middleware/global_error_handler.py` ✅
- `docs/PHASE_2_CONSISTENCY_AUDIT.md` ✅
- `docs/PHASE_2_WEEK_1_IMPLEMENTATION_PLAN.md` ✅ (this file)

**To Modify Next:**
- `backend/app/main.py` — register middleware
- `backend/app/api/dependencies.py` — add correlation_id dependency
- `backend/app/api/routes/tenants.py` — migrate as PoC (or another simple route)
- `backend/tests/unit/test_consistency_helpers.py` — tests

---

## Open Questions / Unknowns

1. **Is GlobalErrorHandlerMiddleware order correct?**
   - Should be first (outermost) in middleware chain
   - But need to check if tenant middleware order matters

2. **How to handle correlation_id in Celery tasks?**
   - Need to extend `app/tasks.py` to set correlation_id context

3. **Which routes should be first to migrate?**
   - Recommend: routes with simple logic (not complex orchestration)
   - Good candidates: documents, training, ppe, tenants

4. **How to test middleware integration?**
   - May need to mock request context in tests

---

## References

- Audit findings: `docs/PHASE_2_CONSISTENCY_AUDIT.md`
- Plan overview: `docs/ENTERPRISE_USABILITY_PLAN.md` (Phase 2 section)
- Next steps: `docs/ENTERPRISE_USABILITY_NEXT_STEPS.md`

---

**Status:** Ready for integration + route migration  
**Next Milestone:** Week 2 — All routes migrated to consistent error format
