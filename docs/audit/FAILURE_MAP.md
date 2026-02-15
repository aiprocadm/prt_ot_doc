# FAILURE_MAP

## Fail-first run (as newcomer)
Date: 2026-02-15

Executed commands:
1. `make cs:reset`
2. `cp .env.example .env`
3. `make install`
4. `npm --prefix frontend ci`
5. `pytest --collect-only -q`
6. `source .venv/bin/activate && pytest --collect-only -q`
7. `make cs:test`
8. `timeout 40s make cs:dev`

## Observed failures and risks

### P0-1: `pytest` command from global shell may fail in clean Codespaces
- Symptom: `pytest --collect-only -q` failed with `ModuleNotFoundError: No module named 'pytest_asyncio'`.
- Root cause: dependencies are installed inside `.venv`, but plain shell `pytest` resolved to host/global interpreter.
- Mitigation: docs now require `source .venv/bin/activate && pytest --collect-only -q` for CLI discovery.

### P0-2: Test defaults referenced external infra endpoints
- Risk: `sitecustomize.py` + `vscode_pytest.py` had Redis/MinIO-like defaults (`redis://...`, `http://localhost:9000`) which can produce flaky discovery behavior.
- Fix: centralized in-memory/local defaults in `test_env_defaults.py` and reused in both bootstrap files.

### P1-1: `dev_lite.sh` always deleted sqlite db
- Symptom: every `make cs:dev` reset local state (`dev.db`) unconditionally.
- Fix: `KEEP_DB=1 make cs:dev` now preserves DB.

### P1-2: Poetry/pip dual sources of dependency truth
- Symptom: repo contained both `poetry.lock` and `requirements*.txt`, while Makefile/CI/dev scripts are pip-based.
- Fix: kept single onboarding path (pip + requirements), removed Poetry lock and Poetry sections from onboarding metadata.

## Validation after fixes
- `source .venv/bin/activate && pytest --collect-only -q` → passes.
- `make cs:test` → backend + frontend tests pass.
- `make cs:dev` starts backend/frontend, prints backend readiness and `Admin created/exists` with dev bootstrap.
