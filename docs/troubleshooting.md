# Troubleshooting Guide

Quick reference for common issues when setting up and running the PRT OT DOC platform.

## Setup & Installation

### Python version mismatch

**Error:** `pip install` fails with `ERROR: No matching distribution found` or `ModuleNotFoundError` for `asyncpg`.

**Cause:** Python version mismatch. The project requires **Python 3.12** to match CI and Docker.

**Solution:**
```bash
python --version  # Verify you have 3.12.x
python3.12 -m venv .venv  # Explicit version
source .venv/bin/activate
pip install -r requirements.txt
```

In **WSL**, ensure dependencies are installed **inside the selected Linux distro**:
```bash
wsl --list -v  # See active distro
wsl --distribution Ubuntu pip install python3.12
```

---

### Virtual environment not activated

**Error:** `ModuleNotFoundError` when running Python, or commands like `pytest` not found.

**Solution:**
```bash
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows CMD
# or PowerShell
.venv\Scripts\Activate.ps1
```

Verify activation: prompt should show `(.venv)` prefix.

---

### Missing Node.js or npm version mismatch

**Error:** `npm: command not found` or `npm --prefix frontend install` fails.

**Cause:** Node.js not installed or version too old (project uses Node 18+).

**Solution:**
```bash
node --version  # Check version
npm --version

# Install Node 18+ from https://nodejs.org/
# Then verify:
npm --prefix frontend ci  # Clean install per package-lock.json
```

---

## Environment & Configuration

### Missing `.env` file

**Error:** Backend won't start; complaints about `SECRET_KEY` or database URL.

**Cause:** `.env` file not found.

**Solution:**
```bash
cp .env.example .env
# Review default values; for local dev, most defaults are safe
cat docs/ENV_REFERENCE.md  # Understand each variable
```

---

### Database connection refused

**Error:** `psycopg2.OperationalError` or `Error connecting to database` when starting backend.

**Cause:** Database service not running, wrong `DATABASE_URL`, or port conflict.

**Solution:**
```bash
# For dockerless setup (SQLite):
# Ensure .env has DATABASE_URL=sqlite:///./app.db

# For PostgreSQL (Docker Compose):
docker-compose up -d postgres redis minio
# Wait 10 seconds for services to start
python scripts/run_backend_lite.py

# Verify database exists:
sqlite3 ./app.db ".tables"  # For SQLite
psql -U postgres -d prt_ot_doc -c "\dt"  # For PostgreSQL
```

---

### Port already in use

**Error:** `Address already in use` for port 8000 (backend) or 5173 (frontend).

**Cause:** Process already running on the port.

**Solution:**

**macOS/Linux:**
```bash
lsof -i :8000    # List process on port 8000
kill -9 <PID>    # Kill process

# Or let the launcher kill it:
python scripts/dev_lite.py --auto-kill-ports
```

**Windows PowerShell:**
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

## Backend Issues

### Migration not applied

**Error:** `sqlalchemy.exc.OperationalError: table "..." does not exist` or migration-related errors.

**Cause:** Alembic migrations not run.

**Solution:**
```bash
export PYTHONPATH=backend  # Set Python path
alembic upgrade head       # Apply all pending migrations

# Verify current schema:
alembic current
alembic history
```

---

### FastAPI import errors

**Error:** `ModuleNotFoundError: No module named 'app'` when running backend.

**Cause:** `PYTHONPATH` not set.

**Solution:**
```bash
export PYTHONPATH=backend  # macOS/Linux
# or
$env:PYTHONPATH="backend"  # PowerShell

# Then start:
python scripts/run_backend_lite.py
```

---

### Tenant header missing

**Error:** `400 Bad Request: X-Tenant header required` from API endpoints.

**Cause:** Your request lacks the required `X-Tenant` header (by design; all business routes require multi-tenancy context).

**Solution:**

1. Log in via UI (Login page auto-sets tenant context).
2. For API calls, include the header:
   ```bash
   curl -H "X-Tenant: demo" -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/documents
   ```
3. Default tenant for dev is `demo` (set via `ADMIN_TENANT` in `.env`).

---

### Secret key or S3 credentials missing at startup

**Error:** Empty warnings or errors about `SECRET_KEY`, `S3_ENDPOINT`, `S3_ACCESS_KEY`.

**Cause:** Optional credentials not set; fallback defaults are used (fine for local dev, not production).

**Solution:**
- For **local development**, empty values are safe (in-memory or local fallbacks).
- For **production**, populate `docs/ENV_REFERENCE.md` secrets before deployment.
- For **test suite**, `tests/conftest.py` normalizes empty credentials to safe defaults.

---

## Frontend Issues

### TypeScript errors in IDE

**Error:** `TS2304: Cannot find name "usePolling"` or similar import errors.

**Cause:** Missing or incorrect import; node_modules stale.

**Solution:**
```bash
npm --prefix frontend ci           # Fresh install
npm --prefix frontend run typecheck  # Full check
```

If still failing, clear cache:
```bash
rm -rf frontend/node_modules frontend/dist
npm --prefix frontend ci
npm --prefix frontend run typecheck
```

---

### Vite dev server error: `ENOENT: no such file or directory`

**Error:** Frontend dev server crashes at startup.

**Cause:** Broken import or missing file in `frontend/src`.

**Solution:**
```bash
npm --prefix frontend run typecheck  # Identify exact error
npm --prefix frontend run lint       # Check ESLint issues

# Review error output; fix import paths or file references
npm --prefix frontend run dev        # Retry
```

---

### ESLint or Prettier violations block build

**Error:** `npm --prefix frontend run build` fails with lint/formatting errors.

**Cause:** Code style issues (unused variables, spacing, etc.).

**Solution:**
```bash
npm --prefix frontend run lint     # See violations
npm --prefix frontend run lint:fix # Auto-fix most issues

# Manually fix any remaining issues, then:
npm --prefix frontend run build
```

---

### Page not loading / blank screen

**Error:** Browser shows blank page or React error in console.

**Cause:** Tenant not selected, authentication expired, or API unavailable.

**Solution:**

1. Open browser DevTools (`F12` → Console tab).
2. Check error messages — look for:
   - `"X-Tenant not set"` → Log in and select tenant.
   - `"401 Unauthorized"` → Session expired; refresh or re-login.
   - `"Failed to fetch from /api/..."` → Backend not running; start it:
     ```bash
     python scripts/run_backend_lite.py
     ```
3. Default login (Codespaces/local dev):
   - Tenant: `demo`
   - Email: `admin@example.com`
   - Password: `admin123`

---

## Testing Issues

### Pytest can't find tests

**Error:** `ERROR: not found: /path/to/tests` or `_pytest.config.PytestConfigError`.

**Cause:** `PYTHONPATH` not set or pytest config issues.

**Solution:**
```bash
export PYTHONPATH=backend  # Set backend as Python module root
pytest -q tests/test_entrypoints.py  # Run a smoke test

# Or use the wrapper script:
bash scripts/pytest.sh tests/test_entrypoints.py
```

---

### Test database locked or stale

**Error:** `sqlite3.OperationalError: database is locked` during `pytest` run.

**Cause:** Concurrent test processes or stale database handle.

**Solution:**
```bash
rm ./app.db  # Remove stale database
pytest -q --forked tests/test_entrypoints.py  # Isolated test runs

# Or restart all Python processes:
pkill -f "python.*pytest"
rm ./app.db
pytest -q tests/test_entrypoints.py
```

---

### Import errors in conftest

**Error:** `ImportError: cannot import name UNSET from click.core` or similar.

**Cause:** Click version mismatch or version-specific API incompatibility.

**Solution:**
```bash
pip install -r requirements.txt -r requirements-dev.txt --force-reinstall
pytest --collect-only tests/test_entrypoints.py  # Validate imports
```

---

## CLI & Scripts

### `ptd` command not found

**Error:** `bash: ptd: command not found` or permission denied.

**Cause:** Script not executable or not in PATH.

**Solution:**
```bash
chmod +x ./ptd
./ptd --help  # Now should work

# Or run directly:
python ./ptd --help
```

---

### Celery worker won't start

**Error:** `Error: Could not instantiate the app` or module import errors in Celery.

**Cause:** `PYTHONPATH` not set or wrong app path.

**Solution:**
```bash
export PYTHONPATH=backend
celery -A app.services.celery_app:celery_app worker --loglevel=info

# For queue-specific workers:
celery -A app.services.celery_app:celery_app worker -Q default,pdf --loglevel=info
```

---

## Documentation & Navigation

### Where's the architecture diagram?

**Answer:** See `docs/ARCHITECTURE.md` for system overview and layer descriptions.

---

### Where's the API specification?

**Answer:** 
- Canonical endpoints: `README.md` (Quick start section).
- Full API docs: Swagger at `http://localhost:8000/docs` (when backend is running).
- API reference: `docs/API_OVERVIEW.md`.

---

### How do I check test coverage?

**Answer:**
```bash
pytest --cov=backend/app/modules --cov-report=html tests/
# Open htmlcov/index.html in browser
```

---

### Where's the requirements matrix?

**Answer:** `docs/spec/TZ_FULL_UNIFIED.md` (product spec) and `docs/audit/TZ_COVERAGE_MATRIX.md` (test/code coverage).

---

## Performance & Optimization

### Backend is slow / high memory usage

**Cause:** Celery tasks piling up, database query inefficiency, or missing indexes.

**Solution:**

1. Check active Celery tasks:
   ```bash
   celery -A app.services.celery_app:celery_app inspect active
   ```
2. Monitor database:
   ```bash
   # SQLite: Check file size
   ls -lh ./app.db
   
   # PostgreSQL: Check slow queries
   psql -U postgres -d prt_ot_doc -c "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 5;"
   ```
3. Profile Python code:
   ```bash
   python -m cProfile -s cumtime scripts/run_backend_lite.py 2>&1 | head -30
   ```

---

### Frontend bundle size too large

**Error:** Build warning: `Bundle size exceeds X MB`.

**Solution:**
```bash
npm --prefix frontend run build -- --analyze  # If available
npm --prefix frontend run typecheck  # Check for dead code
# Review frontend/src for unused imports and dependencies
```

---

## Getting Help

1. **Check existing docs:** `docs/SETUP.md`, `docs/RUNBOOK.md`, `docs/DEMO_ACCESS.md`.
2. **Review CI logs:** `.github/workflows/ci.yml` (shows working commands).
3. **Run smoke tests:** `pytest -q tests/test_entrypoints.py` and `npm --prefix frontend run build`.
4. **Check environment:** Ensure Python 3.12, Node 18+, and correct paths.
5. **Report issues:** Include Python/Node versions, OS, error messages, and reproduction steps.

---

**Last updated:** 2026-05-01  
**Related docs:** [SETUP.md](./SETUP.md), [RUNBOOK.md](./RUNBOOK.md), [ENV_REFERENCE.md](./ENV_REFERENCE.md), [repo-structure.md](./repo-structure.md)
