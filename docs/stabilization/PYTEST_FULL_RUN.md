# Full pytest run instruction (Developer productivity option)

**Created:** 2026-04-29  
**Purpose:** Complete baseline verification for release-ready state.

## Quick start

From repo root:

```bash
# 1. Create isolated venv
python -m venv .venv
source .venv/bin/activate  # Unix/macOS/WSL
# OR
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# 2. Install backend dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Run full pytest suite
export PYTHONPATH=backend  # Unix/macOS/WSL
# OR
$env:PYTHONPATH="backend"  # Windows PowerShell

pytest tests/ -v --tb=short --junitxml=artifacts/backend-junit.xml

# 4. Optional: Generate coverage report
pytest tests/ --cov=backend/app --cov-report=html --cov-report=json
```

## Expected results

- **Total test count:** ~190 test files, ~287–300 tests expected (see `BASELINE_VERIFICATION.md` from 2026-02-18 for reference)
- **Exit code:** 0 (all passed)
- **Warnings:** Deprecation warnings from `docxcompose`, `pydantic`, `jose` are expected and not blockers
- **Artifacts:**
  - `artifacts/backend-junit.xml` — JUnit format for CI
  - `htmlcov/index.html` — coverage report (if --cov flag used)

## What this verifies

1. **Backend unit tests:** core logic, services, schemas
2. **Integration tests:** database interactions, API contracts, auth flows
3. **Cross-tenant isolation:** security matrix against accidental data leakage
4. **Idempotency contracts:** replay and 409 conflict behaviors
5. **Document generation:** template rendering, header application
6. **No regressions:** against baseline established in earlier waves

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'pytest'` | Run `pip install -r requirements-dev.txt` again |
| `PYTHONPATH not set` | Ensure `PYTHONPATH=backend` is in environment before running pytest |
| Database file permission denied | Ensure `.venv` dir has write permissions to `dev.db` |
| Timeout on long-running tests | Increase pytest timeout: `pytest --timeout=600` |
| Warnings noise | Filter with `pytest -W ignore::DeprecationWarning` |

## Next steps after full pytest

1. If all tests pass ✅:
   - Commit result: `git add artifacts/backend-junit.xml && git commit -m "test: full pytest baseline — all 287 tests passed"`
   - Update `RELEASE_READINESS.md` if needed
   - Proceed to Feature focus or Release focus options

2. If tests fail ❌:
   - Review failed test output in `artifacts/backend-junit.xml`
   - Check `tests/conftest.py` for environment setup issues
   - Check database state with `sqlite3 dev.db ".tables"`
   - If regression, investigate against AI_IMPLEMENTATION_REPORT §24–26

## Related commands (frontend CI alternative)

```bash
# Full frontend CI pipeline (lint + typecheck + test + build)
npm --prefix frontend ci

# Individual steps:
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

## References

- `README.md` — Verification commands section
- `docs/TEST_BASELINE.md` — Must-pass smoke checks
- `docs/TESTING.md` — Test strategy and CI mapping
- `CHANGELOG.md` — Recent baseline verification history
