# Baseline verification (fail-first)

**CRITICAL:** This document requires fresh re-verification in a clean Codespace/CI environment before release.
Last verified: 2026-05-02 (полный pytest зафиксирован в секции ниже; 2026-05-01 — обновлены инструкции TZ-1.1, финальная приёмка всё ещё требует чистого прогона в CI/Codespaces)

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
# Restart backend and login

# Step 7: Verify key acceptance scenarios (UI smoke tests)
# In browser at http://localhost:5173:
# - Login flow with test credentials
# - Navigate to documents → see templates
# - Navigate to risks → see dashboard
# - Navigate to training → see list
# - Logout and login again (session persistence)
```

## Full pytest (все `testpaths`) — 2026-05-02, Windows, локальный `.venv`

**Среда:** Windows 10, Python 3.13.7, pytest 8.3.3, корень репозитория, виртуальное окружение `.venv`, `PYTHONPATH=backend`.

**Сборка:** `pytest --collect-only --disable-warnings -o addopts=""` → **1147** тестовых элементов (`tests/`, `integration_tests/`, `backend/tests/` — как в `pyproject.toml`).

**Прогон:** из-за длительности только каталога `tests/` (~64 мин) и неудобной буферизации вывода при длинном пайплайне в PowerShell полный набор выполнен **тремя последовательными командами** (суммарно эквивалент одного `pytest` из корня с теми же `testpaths`):

| Часть | Область | Результат | Примерное время |
|-------|---------|-----------|-----------------|
| 1 | `tests/` | 722 passed, 49 failed, 3 skipped, 2 errors | ~3828 s (~1 ч 4 мин) |
| 2 | `integration_tests/` | 2 passed | ~4 s |
| 3 | `backend/tests/` | 362 passed, 3 failed, 4 skipped | ~58 s |

**Итого (агрегат):** **1086 passed**, **52 failed**, **7 skipped**, **2 errors**; **1147** собранных тестов.

**Артефакты (локально, не в git):** при повторном запуске с `--junit-xml=...` — `artifacts/pytest_part1_tests.xml`, `artifacts/pytest_part2_integration.xml`, `artifacts/pytest_part3_backend_tests.xml` и соответствующие `artifacts/pytest_part*_console.txt` (каталог `artifacts/` в `.gitignore`).

**Группы падений (triage):**

- `tests/test_abac_deny_allow_matrix.py` — серия FAIL по правилам deny/allow и атрибутам ABAC.
- `tests/test_audit_log_immutability.py` — защита UPDATE/DELETE на уровне БД.
- `tests/test_outbox_acceptance_guarantees.py`, `tests/test_outbox_poison_queue_metrics.py` — outbox / poison / дедупликация.
- `tests/test_settings_staging_hardening.py` — отклонение дефолтных секретов и bundled dev JWT в staging-профиле.
- `tests/test_files_tenant_isolation_strict.py` — строгая проверка tenant key в путях файлов.
- `tests/test_tenant_isolation_audit.py` — изоляция по tenant; **2× ERROR** с `ModuleNotFoundError` (`app.domains.integrations`, `app.domains.notifications`) в связке со schemathesis teardown (см. хвост `pytest_part1_console.txt`).
- `tests/api/test_incidents_api.py`, `tests/api/test_risk_events.py`, `tests/test_risk_assessment_kpi5.py` — события / outbox.
- `tests/integration/test_packages_e2e.py` — несколько FAIL по пакетным e2e.
- `backend/tests/e2e/access/test_access_enforcement_matrix.py` — 3 FAIL (Owner/Auditor/Cross-tenant).

**Вывод:** на указанной Windows-среде полный pytest **не зелёный**; для приёмки сравните с прогоном в CI / Linux / Codespaces и устраните расхождения (импорты доменов, staging-конфиг, ABAC/outbox).

## Previous Baseline Run (2026-02-18 — OUTDATED, REQUIRES RE-VERIFICATION)

Дата прогона: 2026-02-18
Среда: GitHub Codespaces / dockerless profile

**Status:** REQUIRES RE-RUN in fresh Codespace environment per TZ-1.1-MVP-01 acceptance criteria. Current metrics from 2026-02-18 may be stale.

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

**Status: PENDING RE-VERIFICATION in fresh environment (Codespaces or CI)**

To complete TZ-1.1-MVP-01, execute in a **fresh GitHub Codespaces environment** or clean CI container:

- [ ] Step 1: `make cs:reset` — State cleaned (dev.db, .local_storage, frontend/coverage removed)
- [ ] Step 2: `cp .env.example .env` — Environment configured
- [ ] Step 3: `make cs:dev` — Backend (port 8000) and Frontend (port 5173) start successfully
- [ ] Step 4: `make cs:test` — All tests pass:
  - Backend pytest: полный набор `testpaths` (см. `pytest --collect-only`; на 2026-05-02 — **1147** элементов; локальный Windows-прогон см. секцию *Full pytest* выше — **не зелёный**, сравнить с CI)
  - Frontend vitest: all tests passed
- [ ] Step 5: `pytest --collect-only -q` — Test collection succeeds without errors
- [ ] Step 6: Login flow verification — `http://localhost:5173` accessible with bootstrap credentials (ADMIN_BOOTSTRAP=1, ADMIN_EMAIL=admin@example.com, ADMIN_PASSWORD=admin123, ADMIN_TENANT=demo)
- [ ] Final: Documentation matches actual commands and output

**Next Agent:** Execute the 6 steps above in a fresh Codespaces environment and update this document with actual results and timestamps. Use this as proof of acceptance for TZ-1.1-MVP-01.
