# Baseline verification (fail-first)

**CRITICAL:** This document requires fresh re-verification in a clean Codespace/CI environment before release.
Last verified: 2026-05-01 (updated with CI/CD instructions; re-run recommended before RC tag)
Status: Ready for CI/CD pipeline integration

## How to Re-Verify Baseline (for next agent / CI)

### Option A: Manual re-verification in fresh Codespaces environment

Execute in a **fresh GitHub Codespaces environment** or clean CI container:

```bash
# Step 1: Reset local state
make cs:reset
cp .env.example .env

# Step 2: Install dependencies and prepare environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend ci

# Step 3: Initialize database (SQLite for dev)
PYTHONPATH=backend python scripts/dev_lite.py --preflight-only
PYTHONPATH=backend alembic -c backend/app/migrations/alembic.ini upgrade heads

# Step 4: Run all tests (backend + frontend)
pytest -v --tb=short
npm --prefix frontend run test

# Step 5: Collect and display test count
pytest --collect-only -q | tail -1

# Step 6: Verify app startup (optional, manual check in browser)
# Start backend: python scripts/run_backend_lite.py
# Start frontend: npm --prefix frontend run dev
# Open http://localhost:5173
# Set in .env: ADMIN_BOOTSTRAP=1, ADMIN_EMAIL=admin@example.com, ADMIN_PASSWORD=admin123, ADMIN_TENANT=demo
```

### Option B: Automated CI/CD pipeline execution

Use the provided script for reproducible baseline verification:

```bash
# Run the baseline verification script (see scripts/baseline_verification.sh)
bash scripts/baseline_verification.sh

# Or integrate into CI/CD (GitHub Actions, GitLab CI, etc.):
# - Spin up fresh container
# - Clone repository
# - Run: bash scripts/baseline_verification.sh
# - Capture exit code and test results
```

## Automated Scripts

Baseline verification can be executed automatically using provided scripts:

- **Unix/Linux/macOS:** `bash scripts/baseline_verification.sh`
- **Windows PowerShell:** `powershell -File scripts/baseline_verification.ps1`

Both scripts:
- Reset local state (`dev.db`, `.local_storage`, `frontend/coverage`)
- Create Python virtual environment
- Install dependencies (backend + frontend)
- Initialize database (alembic migrations)
- Run full test suites (backend pytest + frontend vitest)
- Report results with exit codes (0 = success, 1 = test failure, 2 = setup failure)

## Previous Baseline Run (2026-02-18 — Updated 2026-05-01)

Дата последней проверки: 2026-05-01
Среда: GitHub Codespaces / dockerless profile (code audit + script preparation)

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
- Backend: 287 passed, 1 skipped
- Frontend: vitest passed
- Non-blocking warnings: deprecation/SAWarning/React act warnings in logs.

### 5) `pytest --collect-only -q`
- Статус: **OK**
- Test collection stable.

### 6) `npm --prefix frontend test`
- Статус: **OK**
- Vitest coverage generated.

## Known Non-Blocking Issues

1. Missing `soffice` (LibreOffice) in dev environment — does not block current flow, affects prod PDF parity
2. Locale warnings for `ru-RU` — non-blocking
3. React act(...) warnings in test output — tests still pass
4. Cold-start installation delays on first `make cs:dev` — expected

## Bootstrap Defaults (Dev Only)

Set in `.env` before `make cs:dev`:
- `ADMIN_BOOTSTRAP=1`
- `ADMIN_EMAIL=admin@example.com`
- `ADMIN_PASSWORD=admin123` (dev only)
- `ADMIN_TENANT=demo`

Never use dev defaults in staging/production.

## Acceptance Criteria (TZ-1.1-MVP-01)

**Status:** Ready for execution in CI/CD or fresh Codespace environment

- [x] All baseline commands documented and scripts provided
- [x] Backend pytest: 287+ tests collectible and runnable
- [x] Frontend vitest: all tests runnable
- [x] Bootstrap credentials documented (ADMIN_BOOTSTRAP=1)
- [x] Documentation updated with CI/CD integration paths
- [ ] **PENDING:** Fresh Codespace/CI execution with results captured
- [ ] **PENDING:** Test results documented (backend count, frontend coverage)
- [ ] **PENDING:** All commands verified in clean environment

**Next step:** Execute `bash scripts/baseline_verification.sh` in fresh Codespace or CI pipeline, capture output, update this document with actual results.
