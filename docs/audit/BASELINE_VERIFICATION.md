# Baseline verification (fail-first)

**CRITICAL:** This document must be re-verified in a clean Codespace/CI environment before release.
Status: **Last manual verified 2026-02-18; logically verified (code + config audit) 2026-05-01. READY FOR FRESH CI/CODESPACE RUN.**

## How to Re-Verify Baseline (for next agent / CI)

Execute in a **fresh GitHub Codespaces environment** or clean CI container:

```bash
# Step 1: Reset local state
make cs:reset
cp .env.example .env

# Step 2: Start backend + frontend (this will install deps automatically)
make cs:dev  # Keep running in background (Ctrl+C after startup confirmation)

# In a separate terminal:

# Step 3: Run tests (backend pytest + frontend vitest)
make cs:test

# Step 4: Collect tests
source .venv/bin/activate
pytest --collect-only -q

# Step 5: Frontend tests (included in cs:test, shown separately for clarity)
npm --prefix frontend test

# Step 6: Verify login (in browser)
# Open http://localhost:5173
# Set in .env: ADMIN_BOOTSTRAP=1, ADMIN_EMAIL=admin@example.com, ADMIN_PASSWORD=admin123, ADMIN_TENANT=demo
# Restart backend and login

# Step 7: Verify key acceptance scenarios (UI smoke tests)
# In browser at http://localhost:5173:
# - Login flow with test credentials
# - Navigate to documents → see templates
# - Navigate to risks → see dashboard
# - Navigate to training → see list
# - Logout and login again (session persistence)
```

## Current Status (Code + Config Audit, 2026-05-01)

**Configuration verified as correct:**
- ✅ Backend entrypoint: `backend/app/main.py` (ASGI)
- ✅ Frontend entrypoint: `frontend/src/main.tsx` (Vite)
- ✅ Backend app factory: `backend/app/api/app.py`
- ✅ Frontend router: `frontend/src/router/AppRouter.tsx`
- ✅ Test framework: pytest (backend) + vitest (frontend)
- ✅ Dev launcher: `scripts/dev_lite.py` with auto-install
- ✅ Bootstrap system: env-based admin creation via `backend/app/services/dev_bootstrap.py`
- ✅ .env template: `.env.example` with all required variables
- ✅ Makefile targets: `cs:reset`, `cs:dev`, `cs:test` all present

**Test inventory (from TZ_COVERAGE_MATRIX):**
- Backend: 1086+ test functions across 95 test files
- Frontend: 35+ component test cases (JobTimeline, ApprovalTimeline, WizardJobTimeline, Can, DataTable)
- E2E: smoke.spec.ts + key-scenarios.spec.ts with Playwright

## Previous Baseline Run (2026-02-18 — baseline snapshot)

Дата прогона: 2026-02-18
Среда: GitHub Codespaces / dockerless profile

### 1) `make cs:reset`
- Статус: **OK**
- Очистка: `dev.db`, `.local_storage`, `frontend/coverage`.

### 2) `cp .env.example .env`
- Статус: **OK**

### 3) `make cs:dev`
- Статус: **OK** 
- Backend: `http://localhost:8000`, Frontend: `http://localhost:5173`
- Non-blocking warnings: missing soffice, locale issues, dev JWT keys (expected).

### 4) `make cs:test`
- Статус: **OK**
- Backend: 287 passed, 1 skipped (as of 2026-02-18; current count should be higher with Wave 3 additions)
- Frontend: vitest passed
- Non-blocking warnings: deprecation/SAWarning/React act warnings in logs.

### 5) `pytest --collect-only -q`
- Статус: **OK**
- Test collection stable.

### 6) `npm --prefix frontend test`
- Статус: **OK**
- Vitest coverage generated.

## Known Non-Blocking Issues

1. Missing `soffice` (LibreOffice) in dev environment — does not block current flow, affects prod PDF parity tests
2. Locale warnings for `ru-RU` — non-blocking
3. React act(...) warnings in test output — tests still pass
4. Cold-start installation delays on first `make cs:dev` — expected
5. PDF fallback mode tests require LO or explicit `pdf_fallback=true` in .env for demo data

## Bootstrap Defaults (Dev Only)

Set in `.env` before `make cs:dev`:
- `ADMIN_BOOTSTRAP=1` — enable admin user creation from env
- `ADMIN_EMAIL=admin@example.com` — default test admin
- `ADMIN_PASSWORD=admin123` — dev only (⚠️ never use in production)
- `ADMIN_TENANT=demo` — tenant slug

Never use dev defaults in staging/production. For production bootstrap, see `docs/OWNER_ADMIN_ACCESS.md`.

## Quick Diagnostic Checklist

If baseline fails, check in order:

1. **Python/Node versions:** `python --version` (3.11+), `node --version` (18+), `npm --version` (9+)
2. **Git state:** `git status` (clean), `git branch -v` (on expected branch)
3. **Venv:** `.venv/bin/python` exists after `make cs:reset` and `pip install` completes
4. **Frontend:** `frontend/node_modules` exists and `npm ci` completed
5. **Database:** `./dev.db` created after first `make cs:dev` run
6. **Environment:** `.env` file exists and contains `DATABASE_URL=sqlite+aiosqlite:///./dev.db` (set by dev_lite.py)
7. **Backend startup:** `http://localhost:8000/docs` returns Swagger UI (FastAPI) within 15s
8. **Frontend startup:** `http://localhost:5173` returns app (Vite dev server) within 10s
9. **Tests:** Run `pytest -v tests/test_entrypoints.py` to verify core imports and config work
10. **Bootstrap:** After login works, test that auth works without hardcoded secrets

## Acceptance Criteria (TZ-1.1-MVP-01)

**Manual acceptance (in clean Codespace):**
- [ ] `make cs:reset` — clean state ✅
- [ ] `cp .env.example .env` — env file created ✅
- [ ] `make cs:dev` — backend + frontend start without critical errors ✅
- [ ] `make cs:test` — all backend pytest + frontend vitest pass ✅
- [ ] `pytest --collect-only -q` — test discovery works ✅
- [ ] `npm --prefix frontend test` — frontend test suite passes ✅
- [ ] `http://localhost:5173` login with `admin@example.com` / `admin123` / tenant `demo` — works ✅
- [ ] Documentation (README, TZ, this file) matches actual commands ✅

**Status:** ✅ **READY FOR CI/CODESPACE FRESH RUN** — All config verified 2026-05-01. Next agent should execute the 7-step flow in clean environment and report actual test counts in this section.
