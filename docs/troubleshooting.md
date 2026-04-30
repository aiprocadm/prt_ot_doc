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
Quick diagnostics and fixes for common development issues.

## Table of Contents
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Database and Migrations](#database-and-migrations)
- [Testing](#testing)
- [PDF Generation](#pdf-generation)
- [Multi-tenancy](#multi-tenancy)
- [Performance and Debugging](#performance-and-debugging)
- [CI/CD](#cicd)

---

## Backend Setup

### `pytest: command not found`

**Symptoms:** `pytest --version` or `pytest` commands fail.

**Solution:**
```bash
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt -r requirements-dev.txt
```

Then use:
```bash
export PYTHONPATH=backend  # or $env:PYTHONPATH="backend" on PowerShell
python -m pytest tests/test_entrypoints.py -v
```

### `ModuleNotFoundError: No module named 'backend.app'`

**Symptoms:** Backend starts but imports fail; tests cannot find `app.*` modules.

**Solution:** Set `PYTHONPATH` before running any command:
```bash
export PYTHONPATH=backend  # Unix/macOS
# or
$env:PYTHONPATH="backend"  # PowerShell
```

Alternatively, the CLI wrapper `./ptd` sets this automatically:
```bash
./ptd --help
```

### `KeyError: 'SECRET_KEY'` or empty config values

**Symptoms:** Backend crashes on startup with missing env vars; tests fail on fixtures.

**Solution:**
1. Copy the example environment:
   ```bash
   cp .env.example .env
   ```

2. For development, these values are safe defaults:
   ```bash
   SECRET_KEY=dev-secret-key-for-local-dev-only
   ADMIN_TENANT=demo
   ADMIN_EMAIL=admin@example.com
   ADMIN_PASSWORD=admin123
   ```

3. For tests, use `conftest.py` bootstrap with `ADMIN_BOOTSTRAP=1`:
   ```bash
   export ADMIN_BOOTSTRAP=1
   export ADMIN_TENANT=test_tenant
   python -m pytest tests/test_entrypoints.py -v
   ```

### `SQLAlchemy: No such table: tenants`

**Symptoms:** Backend starts but fails on first business request; "table not found" errors.

**Solution:** Initialize the database schema:
```bash
python scripts/run_backend_lite.py --init-schema
```

Or use the canonical start command:
```bash
make dev-lite
```

### `PYTHONPATH=backend python -m pytest` hangs or timeout

**Symptoms:** Tests hang indefinitely; pytest never completes.

**Solution:**
1. Check for conflicting Celery/Redis processes:
   ```bash
   # Kill any lingering workers
   pkill -f celery
   pkill -f redis
   ```

2. Ensure `DATABASE_URL` points to a valid SQLite file (not in-memory):
   ```bash
   echo $DATABASE_URL  # should be like: sqlite:///./backend.db
   ```

3. Run with a shorter timeout and verbose output:
   ```bash
   python -m pytest tests/test_entrypoints.py -v -s --timeout=10
   ```

### `Click.ParamType error` in CLI tests

**Symptoms:** `test_backup_command_json` or `test_render_command_invokes_pipeline` fail with Click validation.

**Solution:** Ensure Typer/Click versions match `requirements.txt`:
```bash
pip show typer click
# Expected: typer>=0.12, click>=8.0,<9.0
```

If versions mismatch:
```bash
pip install --upgrade -r requirements.txt
python -m pytest tests/test_cli_commands.py::test_backup_command_json -v
```

---

## Frontend Setup

### `npm ERR! code ERESOLVE`

**Symptoms:** `npm ci` fails with dependency resolution error.

**Solution:**
1. Clear npm cache:
   ```bash
   npm cache clean --force
   ```

2. Delete `node_modules` and lockfile, then reinstall:
   ```bash
   rm -rf frontend/node_modules frontend/package-lock.json
   npm --prefix frontend ci
   ```

3. If using npm <8, use legacy peer deps:
   ```bash
   npm --prefix frontend ci --legacy-peer-deps
   ```

### `Cannot find module '@/...'` (path alias error)

**Symptoms:** TypeScript compilation fails; IDE shows red squiggles on imports like `@/hooks/usePolling`.

**Solution:** Ensure `frontend/vite.config.ts` and `frontend/tsconfig.json` are aligned:

1. Check `vite.config.ts` has:
   ```typescript
   resolve: {
     alias: {
       '@': path.resolve(__dirname, './src'),
     },
   }
   ```

2. Check `tsconfig.json` has:
   ```json
   "compilerOptions": {
     "baseUrl": ".",
     "paths": {
       "@/*": ["src/*"]
     }
   }
   ```

3. Rebuild and restart:
   ```bash
   npm --prefix frontend run typecheck
   npm --prefix frontend run dev
   ```

### `npm run lint` fails with `@typescript-eslint/no-unused-vars`

**Symptoms:** Linter reports unused variables or imports; `npm run build` is blocked.

**Solution:** Remove the unused imports or variables, or disable the rule locally if intentional:
```typescript
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const unusedVar = value;
```

Recommended: delete unused code and re-run:
```bash
npm --prefix frontend run lint -- --fix
```

### `vitest: unhandled promise rejection`

**Symptoms:** `npm run test` shows "7 unhandled errors" and exits with code 1; tests pass but overall suite fails.

**Solution:** The error is usually from a missing `X-Tenant` header in API mocks. In test files:
```typescript
beforeEach(() => {
  tenantStorage.setTenant('test-tenant');  // Set tenant context
});
```

Or in test fixtures, ensure `apiClient` is initialized with tenant:
```typescript
const mockClient = createMockApiClient({ tenant: 'test-tenant' });
```

See [`frontend/src/components/pwa/ConflictInboxCard.tsx`](../frontend/src/components/pwa/ConflictInboxCard.tsx) for example of error boundary.

### `npm run build` succeeds but dist/ is empty or incomplete

**Symptoms:** Build completes but `frontend/dist/` is missing or incomplete.

**Solution:**
1. Check for build errors in output (may be suppressed):
   ```bash
   npm --prefix frontend run build 2>&1 | tail -50
   ```

2. Ensure no stale TypeScript cache:
   ```bash
   rm -rf frontend/.vite frontend/dist
   npm --prefix frontend run build
   ```

3. Verify `vite.config.ts` has correct `outDir`:
   ```typescript
   build: {
     outDir: 'dist',
   }
   ```

---

## Database and Migrations

### `alembic: No migrations found`

**Symptoms:** `alembic upgrade head` fails; no migrations are discovered.

**Solution:** Ensure `PYTHONPATH` is set and you're in the correct directory:
```bash
cd backend
export PYTHONPATH=.
alembic upgrade head
```

### `PostgreSQL: connection refused` or `SQLite: database is locked`

**Symptoms:** Backend cannot connect to database; "connection refused" error.

**Solution:**

For SQLite (default dev):
```bash
# Check if database file exists and is writable
ls -la backend.db
chmod 644 backend.db

# If locked, ensure no other process holds it
lsof | grep backend.db
```

For PostgreSQL:
```bash
# Verify connection string
echo $DATABASE_URL
# Expected format: postgresql://user:password@localhost:5432/prt_ot_doc

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

### `Migration: can't execute due to existing data`

**Symptoms:** Alembic migration fails with "can't drop column" or "can't add NOT NULL column".

**Solution:**
1. Check the specific migration error:
   ```bash
   export PYTHONPATH=backend
   alembic upgrade head --sql  # View SQL without executing
   ```

2. For data-blocking migrations, use a multi-step approach:
   - Add the column as nullable
   - Backfill data
   - Add the NOT NULL constraint

See `backend/app/migrations/versions/` for examples of safe migration patterns.

---

## Testing

### `tests/test_entrypoints.py` passes but full `pytest` fails

**Symptoms:** Smoke tests pass, but running `pytest tests/` causes failures in unrelated tests.

**Solution:**
1. Check for test isolation issues; ensure tests don't share state:
   ```bash
   python -m pytest tests/test_entrypoints.py tests/api/test_branding_api.py -v --tb=short
   ```

2. If failures appear only in full run, there's likely test order dependency:
   ```bash
   python -m pytest tests/ -v --random-order  # Randomize order to detect dependency
   ```

3. Review conftest.py fixtures for cleanup:
   - Ensure `session` fixture rolls back transactions
   - Ensure `client` fixture clears state between tests

### `test_login_rate_limit` fails with 429 instead of 200

**Symptoms:** Rate limiter test fails; test expects 200 but gets 429 (rate limited).

**Solution:**
1. The limiter needs to be reset before each test:
   ```python
   @pytest.fixture(autouse=True)
   def reset_rate_limiter():
       limiter.reset()  # Reset before each test
       yield
   ```

2. If using `@app.limiter` decorator, ensure the fixture calls the correct reset method.

3. Check for state leakage from previous tests:
   ```bash
   python -m pytest tests/test_rate_limit.py::test_login_rate_limit -v -s
   ```

### `test_jobs_ws_stream_endpoint` fails with PermissionError

**Symptoms:** WebSocket test fails; `PermissionError` on socket creation.

**Solution:** WebSocket tests often require special HTTPX client configuration:
```python
@pytest.fixture
async def ws_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

async def test_ws_endpoint(ws_client):
    async with ws_client.websocket_connect("/api/v1/jobs/ws") as ws:
        # Test code
```

Ensure:
1. The AsyncClient is properly configured for WebSocket
2. The WebSocket route is registered correctly
3. On Windows, check for file descriptor limits: `setx PYTHONIOENCODING=utf-8`

---

## PDF Generation

### `PDF generation times out or fails silently`

**Symptoms:** Document status stays "processing" indefinitely; no PDF output.

**Solution:**
1. Check LibreOffice is installed and configured:
   ```bash
   which libreoffice  # Unix/macOS
   where soffice      # Windows
   echo $LIBREOFFICE_BIN  # Check env var
   ```

2. Verify PDF timeout configuration (default: 120 seconds):
   ```bash
   echo $PDF_LIBREOFFICE_TIMEOUT_SECONDS
   # If > 300, reduce to 120 for faster feedback
   ```

3. Check Celery worker is running:
   ```bash
   export PYTHONPATH=backend
   celery -A app.services.celery_app:celery_app worker --loglevel=info -Q pdf
   ```

4. Review worker logs for stack traces:
   ```bash
   # Worker logs usually go to stdout; check for errors like:
   # "LibreOffice initialization failed"
   # "Cannot find fonts"
   ```

### `Fonts not embedded in PDF`

**Symptoms:** Generated PDF displays correctly locally but fonts fallback on other machines.

**Solution:**
1. Ensure fonts are available and configured:
   ```bash
   echo $FONTS_PATH
   ls -la $FONTS_PATH  # Check directory exists
   ```

2. Verify fonts include DejaVu, Noto Sans (required):
   ```bash
   fc-list | grep -i dejavu   # Unix/macOS
   # On Windows, check C:\Windows\Fonts for "Noto Sans*"
   ```

3. Check LibreOffice is configured to embed fonts:
   ```python
   # In backend/app/modules/pdf/service_pool.py
   # Ensure font embedding is enabled in conversion options
   ```

---

## Multi-tenancy

### `X-Tenant header missing` or `400: Invalid tenant`

**Symptoms:** All API calls to `/api/v1/...` return 400 or 401; frontend shows "Select tenant" error.

**Solution:**
1. The tenant context is required for all business operations:
   ```bash
   curl -H "X-Tenant: demo" http://localhost:8000/api/v1/companies
   # Without header: 400 Bad Request
   ```

2. Frontend should set tenant before making API calls:
   ```typescript
   // frontend/src/api/client.ts
   apiClient.defaults.headers['X-Tenant'] = tenantStorage.getTenant();
   ```

3. Check `tenantStorage` is initialized:
   ```bash
   # In browser console:
   console.log(JSON.parse(localStorage.getItem('tenant_context')));
   # Should show: { tenant_id: "demo", ... }
   ```

### Database `search_path` not updated for tenant

**Symptoms:** Queries cross tenant boundaries; data leaks between organizations.

**Solution:**
1. Ensure middleware sets `search_path`:
   ```python
   # backend/app/middleware/tenant.py
   # Verify set_tenant_search_path() is called for every request
   ```

2. Check database session is scoped to tenant:
   ```bash
   # In backend logs, look for:
   # "Setting search_path to public,tenant_demo"
   ```

3. Run isolation test:
   ```bash
   export PYTHONPATH=backend
   python -m pytest tests/test_tenant_header_required.py -v
   ```

---

## Performance and Debugging

### Backend response is slow (>1 second)

**Symptoms:** API endpoints take too long; frontend feels sluggish.

**Solution:**
1. Enable query logging to find slow queries:
   ```bash
   export SQLALCHEMY_ECHO=true
   python scripts/run_backend_lite.py
   # Watch for SELECT queries with many rows
   ```

2. Check for N+1 queries (multiple queries where one would suffice):
   ```python
   # Review loader strategy in models:
   # from sqlalchemy.orm import selectinload
   # query = session.query(Company).options(selectinload(Company.sites))
   ```

3. Add pagination to list endpoints if returning many rows:
   ```python
   # Check API route uses `skip` and `limit` parameters
   ```

### Memory usage grows unbounded

**Symptoms:** Backend process memory keeps growing; eventual OOM.

**Solution:**
1. Check for session leaks (unclosed database connections):
   ```bash
   # Ensure sessionmaker uses expire_on_commit=False for read-only queries
   ```

2. Monitor Celery task queue:
   ```bash
   export PYTHONPATH=backend
   celery -A app.services.celery_app:celery_app inspect active
   # If many old tasks stuck, investigate task timeout
   ```

3. Check for circular imports or cached references:
   ```bash
   python -c "import backend.app.main; print('OK')"
   ```

### Cannot debug in VS Code

**Symptoms:** Breakpoints not hit; debugger won't connect.

**Solution:**
1. Install debugpy:
   ```bash
   pip install debugpy
   ```

2. Add to your startup script before running backend:
   ```python
   import debugpy
   debugpy.listen(("localhost", 5678))
   ```

3. Configure `.vscode/launch.json`:
   ```json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Python: Backend",
         "type": "python",
         "request": "attach",
         "port": 5678,
         "host": "localhost"
       }
     ]
   }
   ```

---

## CI/CD

### `GitHub Actions: CI fails but local tests pass`

**Symptoms:** Tests pass locally but fail in CI pipeline.

**Solution:**
1. Check Python version mismatch (CI uses Python 3.12):
   ```bash
   python --version  # Should be 3.12.x
   ```

2. Ensure dependencies are identical:
   ```bash
   pip freeze > /tmp/local-deps.txt
   # Compare with requirements.txt
   ```

3. Check for environment variable differences:
   ```bash
   # CI sets DEFAULT_TENANT_SLUG=demo by default
   export DEFAULT_TENANT_SLUG=demo
   ```

4. Re-run failing test locally with exact CI command:
   ```bash
   export PYTHONPATH=backend
   python -m pytest tests/test_cli_commands.py::test_backup_command_json -v --tb=short
   ```

### `npm run ci` fails in CI but `npm run build` passes locally

**Symptoms:** CI job fails on linting/testing but local build works.

**Solution:**
1. Ensure you're running the full CI suite locally:
   ```bash
   npm --prefix frontend ci  # Clean install like CI
   npm --prefix frontend run lint
   npm --prefix frontend run typecheck
   npm --prefix frontend run test  # vitest
   npm --prefix frontend run build
   ```

2. Check for environment-specific issues (Windows vs. Unix line endings):
   ```bash
   # Ensure .gitattributes is correct
   git config core.safecrlf true
   ```

3. Review CI job output for specific error:
   ```bash
   # Look for "error" or "fail" in job logs
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
If none of these solutions work:

1. **Reproduce in clean environment:**
   ```bash
   make cs:reset
   make cs:dev
   make cs:test
   ```

2. **Check canonical documentation:**
   - `README.md` — Quick start and structure
   - `docs/SETUP.md` — Detailed setup instructions
   - `docs/RUNBOOK.md` — Operational procedures
   - `docs/TESTING.md` — Testing strategy and commands

3. **Enable verbose logging:**
   ```bash
   export DEBUG=true
   export SQLALCHEMY_ECHO=true
   export LOGLEVEL=DEBUG
   # Then run your command
   ```

4. **Check release blockers:**
   - Known limitations: `KNOWN_LIMITATIONS.md`
   - Release blockers: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`
   - GAP report: `GAP_REPORT.md`

5. **Run diagnostic script:**
   ```bash
   python scripts/repo_audit.py
   # Generates detailed report to docs/audit/REPOSITORY_AUDIT.md
   ```
