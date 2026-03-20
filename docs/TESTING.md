# TESTING

Canonical testing guide for the repository. This document is the source of truth for backend, frontend, contract, migration, and smoke validation commands.

> Legacy note: `docs/testing.md` is kept only as a compatibility pointer for older links. New references should use `docs/TESTING.md`.

## 1. Test roots and ownership

- Backend/API/unit/integration tests: `tests/`
- Cross-cutting integration scenarios: `integration_tests/`
- Frontend unit/component/router tests: `frontend/src/__tests__/`
- Domain-specific backend tests also exist under `backend/tests/` for legacy module coverage and should still be preserved where active.

## 2. Recommended local workflow

### Backend environment bootstrap
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic -c backend/app/migrations/alembic.ini upgrade head
```

### Frontend environment bootstrap
```bash
npm --prefix frontend ci
```

## 3. Backend test commands

### Fast sanity checks
```bash
pytest -q tests/test_entrypoints.py
pytest -q tests/api/test_branding_api.py
pytest -q tests/headers/test_engine.py
```

### Pytest via helper script
Use the helper when you want reproducible local execution inside the project virtualenv.

```bash
./scripts/pytest.sh --collect-only -q
./scripts/pytest.sh tests/test_idempotency.py -q
```

`./scripts/pytest.sh` is preferred over raw system `pytest` when the shell environment is not guaranteed to be activated.

### Cross-cutting regression slices
```bash
./scripts/pytest.sh tests/test_errors.py tests/e2e/final_regression/test_final_regression_api.py
./scripts/pytest.sh tests/integration/test_tenant_isolation.py tests/integration/test_abac_query_isolation.py
./scripts/pytest.sh tests/test_idempotency.py tests/integration/test_idempotency_generate.py tests/integration/test_pipeline_idempotency.py
./scripts/pytest.sh tests/integration/test_job_status_flow.py tests/test_outbox_dispatch.py tests/test_webhooks_dispatch.py
./scripts/pytest.sh tests/contract/test_openapi_contract.py
```

## 4. Frontend test and build commands

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

If you want a tighter UX-focused subset for critical wizards and route availability:

```bash
cd frontend && npx vitest run GeneratePackWizardPage DocumentsWizardPage AppRouterSmoke
```

## 5. Contract, audit, and documentation checks

```bash
PYTHONPATH=backend python scripts/contract/validate.py
PYTHONPATH=backend python scripts/repo_audit.py
pytest -q tests/e2e/test_release_candidate_docs.py
```

## 6. Migrations, workers, and smoke scenarios

### Database migrations
```bash
alembic -c backend/app/migrations/alembic.ini upgrade head
```

### Worker startup smoke
```bash
celery -A backend.app.worker worker --loglevel=info
```

### Branded document smoke
```bash
PYTHONPATH=backend python scripts/branded_document_smoke.py
make branded-smoke
```

### Broader smoke bundle
```bash
python scripts/pilot_readiness.py
python scripts/perf/api_load.py --help
make final-acceptance
```

## 7. What each category validates

- **Entry point tests** validate backend startup wiring and canonical runtime roots.
- **Branding/document/header tests** validate the document-core path that currently receives the strongest production hardening.
- **Contract tests** validate OpenAPI and machine-facing stability.
- **Tenant/idempotency/outbox tests** validate multi-tenant and reliability guarantees.
- **Frontend typecheck/test/build** validate route composition, permissions-aware rendering foundations, and production bundling.
- **Repo audit and docs tests** validate that the repository explains itself and that key documentation artifacts are present.

## 8. Discovery and VS Code notes

- Python interpreter should point to `${workspaceFolder}/.venv/bin/python`.
- Pytest discovery roots: `tests`, `integration_tests`.
- Frontend discovery root: `frontend/src/__tests__/`.
- Test defaults for local discovery are stabilized by the repo test bootstrap helpers noted in the legacy testing docs and Python test configuration.

## 9. Acceptance references

- Acceptance scenario mapping: `ACCEPTANCE_TEST_MATRIX.md`
- TZ-to-code coverage mapping: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Repository structure audit: `docs/audit/REPOSITORY_AUDIT.md`
- Release decision record: `RELEASE_READINESS.md`
