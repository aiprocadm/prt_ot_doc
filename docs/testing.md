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
PYTHONPATH=backend python scripts/repo_audit.py  # regenerates markdown + JSON audit artifacts
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
- **Repo audit and docs tests** validate that the repository explains itself, that key documentation artifacts are present, and that the machine-readable audit snapshot remains canonical.

## 8. Discovery and VS Code notes

- Python interpreter should point to `${workspaceFolder}/.venv/bin/python`.
- Pytest discovery roots: `tests`, `integration_tests`.
- Frontend discovery root: `frontend/src/__tests__/`.
- Test defaults for local discovery are stabilized by the repo test bootstrap helpers noted in the legacy testing docs and Python test configuration.

## 9. Acceptance references

- Acceptance scenario mapping: `ACCEPTANCE_TEST_MATRIX.md`
- TZ-to-code coverage mapping: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Repository structure audit: `docs/audit/REPOSITORY_AUDIT.md`
- Machine-readable repository audit: `docs/audit/REPOSITORY_AUDIT.json`
- Release decision record: `RELEASE_READINESS.md`

## 10. 2026-03-23 corporate-readiness hardening slice
```bash
pytest -q backend/tests/test_pwa_sync_bootstrap.py backend/tests/test_document_jobs_required.py backend/tests/test_corporate_readiness_hardening.py
python -m compileall backend/app/api/routes/pwa_sync.py backend/app/api/routes/integration_readiness.py
```

## 11. 2026-03-21 focused hardening slice
```bash
pytest -q backend/tests/test_notifications_service.py
pytest -q backend/tests/test_next66_workflow_notifications_npa.py
ruff check backend/app/modules/notifications backend/app/api/routes/notifications.py backend/tests/test_notifications_service.py
python -m compileall backend/app/modules/notifications backend/app/api/routes/notifications.py backend/tests/test_notifications_service.py
```
# Тестирование (канонический гайд)

Короткие пути в репозитории; детализация по слоям — в `docs/TEST_BASELINE.md`, `docs/CI_PIPELINE_OVERVIEW.md`, `docs/stabilization/`.

## Локальная проверка (как в README)

**Backend (из корня репозитория):**

```bash
# Windows PowerShell
$env:PYTHONPATH = "backend"
.venv/Scripts/python.exe -m pytest -q

# Unix
export PYTHONPATH=backend
python -m pytest -q
```

**Точечно (KPI P0 / tenant / idempotency / шаблоны):**

```bash
pytest -q tests/test_tenant_header_required.py tests/test_idempotency.py tests/test_template_delete.py
```

**Frontend:** `npm --prefix frontend run ci` (или по отдельности `typecheck`, `test`, `build` — см. `frontend/package.json`).

## Полный pytest (зафиксированный прогон)

Актуальные цифры, разбивка по каталогам и группы падений: **`docs/audit/BASELINE_VERIFICATION.md`** — секция *Full pytest (все `testpaths`) — 2026-05-02*.

Кратко (Windows, Python 3.13.7, агрегат трёх прогонов = полный `testpaths`): **1147** собрано, **1086** passed, **52** failed, **7** skipped, **2** errors.

## Среда pytest

`tests/conftest.py` задаёт тестовые `DATABASE_URL` (sqlite), Redis memory, плейсхолды для S3; при пустом `SECRET_KEY` в окружении выставляется безопасное тестовое значение, чтобы `bootstrap("api")` не падал.

## CI

Сводка: `docs/CI_PIPELINE_OVERVIEW.md` (файл `.github/workflows/ci.yml` — backend pytest, фронт `npm run ci`, compose smoke).

## Матрицы и приёмка

- Критерии must-pass: `docs/TEST_BASELINE.md`
- E2E политика: `docs/stabilization/e2e-access.md`
- Соответствие ТЗ (сводно): `docs/audit/TZ_COMPLIANCE.md`, `docs/audit/TZ_COVERAGE_MATRIX.md`

