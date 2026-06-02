# iter38 Enum `server_default` Canonical-PG Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `alembic upgrade heads` succeed on a fresh Postgres 16 by correcting 18 invalid `server_default` literals in the iter38 migration, so the backend can boot on PG — the single hard gate blocking canonical CI re-validation.

**Architecture:** One migration file is edited (18 enum-column `server_default` literals changed from UPPER_CASE member *names* to the lowercase *values* the enums actually store). The existing AST pin test's `_COHORT_C` table is updated to match. A new `@pytest.mark.db` guard test executes the full upgrade against a throwaway PG database — the first PG-executing test in the suite (everything else runs on SQLite, where the bug is invisible). The `server_default_parity` audit is unaffected (it credits presence, not value).

**Tech Stack:** Python 3.12.12 (canonical; local verification on 3.13.7 via `.venv`), Alembic 1.13.3, SQLAlchemy 2 + asyncpg, Postgres 16 (local docker container `promtech-cabinet-db-1`, `postgres/postgres@localhost:5432`).

**Spec:** `docs/superpowers/specs/2026-05-31-enum-server-default-canonical-pg-fix-design.md`

---

## ✅ STATUS: COMPLETE (2026-06-02)

All 6 tasks delivered. Scope expanded during execution from the planned 1-layer enum
`server_default` fix to a **5-layer** migration cascade (each PG-only bug masked the next).

- **Task 1–4** (guard test, 18 `server_default` corrections, `_COHORT_C` pin sync, app-free regression) — commit `54cae5c`. Guard green: `alembic upgrade heads` exit 0, 106 migrations on fresh PG16; app-free 337+117 passed.
- **Task 5–6** (release docs, final canonical run + handoff) — commit `e0bc078`.
- **env.py** changed to `AUTOCOMMIT` + `transaction_per_migration` (layer 2) to allow `ALTER TYPE ADD VALUE`; iter47/iter42 explicit enum `create()` (layers 3/5); iter43 PG default-dance (layer 4).

**Post-completion (2026-06-02 session, executing-plans continuation):**
- **Pre-merge risk review of the env.py atomicity change — DONE.** Verdict: acceptable for merge (per-*statement* autocommit proven; no migration depends on global rollback; all 7 `ADD VALUE` are `IF NOT EXISTS`). See `AI_IMPLEMENTATION_REPORT.md` top handoff + `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.
- **Downgrade tested on PG.** Fixed an asymmetry this plan's `54cae5c` introduced: iter43 `downgrade()` now mirrors the upgrade's DROP DEFAULT→retype→SET DEFAULT before `DROP TYPE`. Pre-existing downgrade gaps (next63 `version_num`, iter41 `journaltype`) logged as a separate "downgrade repair" follow-up (not release-blocking).
- **🔴 New finding (separate plan):** 49/81 ORM native-enum columns lack `values_callable` → SQLAlchemy stores UPPER member *names* while the pg_enum types hold lowercase *value* labels → inserts fail on PG. Out of scope for this plan; spawned as its own task.

The step checkboxes below are left unticked for historical fidelity; this banner is the authoritative completion record.

---

## File Structure

- **Modify:** `backend/app/migrations/versions/20260529_iter38_server_default_cohort_c.py` — fix 18 `server_default` literals in `upgrade()`. (Downgrade unchanged — it sets `server_default=None`.)
- **Modify:** `backend/tests/test_iter38_server_default_cohort.py` — update 18 rows of `_COHORT_C` to the corrected lowercase literals.
- **Create:** `backend/tests/test_alembic_postgres_upgrade.py` — new `@pytest.mark.db` guard that runs `alembic upgrade heads` on a fresh PG, skipped when `TEST_PG_ADMIN_URL` is unset.
- **Modify (docs):** `KNOWN_LIMITATIONS.md`, `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` — replace the stale `DuplicateObjectError` note with the real (now-fixed) iter38 case-mismatch.

**Verification environment (local):** throwaway DB on the running PG16 container; never touch the `cabinet` DB.
```
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/alembic_verify"
$env:PYTHONPATH   = "D:\Кодинг\Создание платформы по ОТ\backend"
# recreate fresh each run:
docker exec promtech-cabinet-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS alembic_verify;"
docker exec promtech-cabinet-db-1 psql -U postgres -c "CREATE DATABASE alembic_verify;"
```
Run pytest via the **PowerShell tool + `.venv\Scripts\python.exe`**, redirecting to a file (git-bash hangs; see project memory). Canonical Py3.12.12 confirmation happens in CI.

---

## Task 1: Add the Postgres upgrade guard test (RED)

**Files:**
- Create: `backend/tests/test_alembic_postgres_upgrade.py`

- [ ] **Step 1: Write the guard test**

```python
"""DB guard: full ``alembic upgrade heads`` must succeed on a fresh Postgres.

This is the ONLY test that exercises migrations against real PG enum types.
The rest of the suite runs on SQLite, where ``Enum`` columns degrade to
VARCHAR and accept any string — which is exactly why the iter-38
``server_default`` case-mismatch (``'PENDING'`` vs enum label ``pending``)
shipped undetected and broke backend boot on Postgres.

Skips unless ``TEST_PG_ADMIN_URL`` points at a Postgres superuser/owner
connection (a maintenance DB such as .../postgres) able to CREATE/DROP
databases. Locally: ``postgresql://postgres:postgres@localhost:5432/postgres``.
CI sets it to the job's Postgres service.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "app" / "migrations" / "alembic.ini"
SCRIPT_LOCATION = REPO_ROOT / "backend" / "app" / "migrations"


def _async_url(admin_url: str, dbname: str) -> str:
    base = admin_url.rsplit("/", 1)[0]  # strip the maintenance db segment
    base = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the Postgres migration guard")
def test_alembic_upgrade_heads_on_fresh_postgres() -> None:
    import asyncpg
    from alembic import command
    from alembic.config import Config

    dbname = f"alembic_guard_{uuid.uuid4().hex[:12]}"

    async def _exec(sql: str) -> None:
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        os.environ["DATABASE_URL"] = _async_url(ADMIN_URL, dbname)
        # env.py reads settings.database_url; settings is cached — force a re-read.
        from app.core.config import get_settings

        get_settings.cache_clear()

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
        command.upgrade(cfg, "heads")  # raises on the first failing migration
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
```

- [ ] **Step 2: Run the guard test against PG — confirm it FAILS on the bug**

PowerShell:
```powershell
$env:TEST_PG_ADMIN_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
$out = "$env:TEMP\guard_red.txt"; if (Test-Path $out){Remove-Item $out}
& ".venv\Scripts\python.exe" -u -m pytest backend/tests/test_alembic_postgres_upgrade.py -p no:cacheprovider -q -o addopts="" > $out 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $out -Tail 15
```
Expected: **FAIL** — `sqlalchemy ... InvalidTextRepresentationError: invalid input value for enum approvalprocessstatus: "PENDING"` (from `20260529_iter38_server_default_cohort_c.py`). This proves the guard catches the bug. Do **not** commit yet (test + fix commit together in Task 2).

---

## Task 2: Correct the 18 invalid `server_default` literals (GREEN)

**Files:**
- Modify: `backend/app/migrations/versions/20260529_iter38_server_default_cohort_c.py` (in `upgrade()` only)

The 15 already-valid columns (4 plain `varchar`; 10 UPPER_CASE-storing enums `equipment/idempotency_keys/incident.severity/npa/permit/pipeline_runs/plantask/ppeissue/template/templateversion`; and `tenant.kind="customer"`) are **left unchanged**. Change only these 18, each derived from live `pg_enum` labels:

- [ ] **Step 1: Apply the 18 exact replacements** (each is a unique `server_default="…"` line inside its labelled `op.alter_column(<table>, <column>, …)` block):

| table.column | change |
|---|---|
| approval_processes.status | `server_default="PENDING"` → `server_default="pending"` |
| approval_tasks.status | `server_default="OPEN"` → `server_default="open"` |
| attestation.status | `server_default="ACTIVE"` → `server_default="active"` |
| client_request_tickets.status | `server_default="OPEN"` → `server_default="open"` |
| edo_envelopes.status | `server_default="QUEUED"` → `server_default="queued"` |
| inspection_prescription.status | `server_default="OPEN"` → `server_default="open"` |
| pack_run_items.status | `server_default="QUEUED"` → `server_default="queued"` |
| pack_runs.status | `server_default="QUEUED"` → `server_default="queued"` |
| package_preset_items.output_format | `server_default="BOTH"` → `server_default="both"` |
| package_preset_items.replace_mode | `server_default="NONE"` → `server_default="none"` |
| package_presets_v2.source_type | `server_default="CSV"` → `server_default="csv"` |
| package_presets_v2.status | `server_default="DRAFT"` → `server_default="draft"` |
| package_profiles_v2.status | `server_default="DRAFT"` → `server_default="draft"` |
| package_requirements.status | `server_default="MISSING"` → `server_default="missing"` |
| package_requirements.type | `server_default="FILE"` → `server_default="file"` |
| package_runs.status | `server_default="DRAFT"` → `server_default="draft"` |
| ppeitem.category | `server_default="OTHER"` → `server_default="other"` |
| training_session.status | `server_default="SCHEDULED"` → `server_default="scheduled"` |

> Because several blocks share a literal (e.g. three `"QUEUED"`, three `"DRAFT"`), edit by locating the `op.alter_column("<table>", "<column>", …)` block first, then change its `server_default=` line — do not blind-replace-all. The `downgrade()` block is untouched (it uses `server_default=None`).

- [ ] **Step 2: Re-run the guard test — confirm it PASSES**

PowerShell (same env as Task 1 Step 2):
```powershell
$out = "$env:TEMP\guard_green.txt"; if (Test-Path $out){Remove-Item $out}
& ".venv\Scripts\python.exe" -u -m pytest backend/tests/test_alembic_postgres_upgrade.py -p no:cacheprovider -q -o addopts="" > $out 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $out -Tail 8
```
Expected: **PASS** (`1 passed`) — `alembic upgrade heads` runs clean through all heads on a fresh PG. If a *new* failure surfaces on a migration **after** iter38, stop and re-scope (spec "Risks": the single-transaction rollback hides anything past the first failure).

- [ ] **Step 3: Commit the fix + guard together**

```bash
git add backend/app/migrations/versions/20260529_iter38_server_default_cohort_c.py backend/tests/test_alembic_postgres_upgrade.py
git commit -m "fix(migrations): correct iter38 enum server_default to real lowercase labels

18 enum columns set server_default to UPPER_CASE member names, but the
enums store lowercase values (values_callable) -> InvalidTextRepresentationError
on PG, blocking backend boot. Corrected to valid labels; add a @pytest.mark.db
guard that runs `alembic upgrade heads` on a fresh Postgres (the suite is
otherwise SQLite-only, which hid the bug).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Sync the iter38 AST pin test + confirm the parity audit still passes

**Files:**
- Modify: `backend/tests/test_iter38_server_default_cohort.py` (`_COHORT_C`, lines ~48-82)

`test_cohort_column_server_default_matches_model` asserts the migration's `server_default` source equals the literal in `_COHORT_C`. After Task 2 those 18 must change to lowercase; the other 15 rows stay.

- [ ] **Step 1: Update the 18 corrected rows in `_COHORT_C`** (change only the final tuple element):

```python
    ("approval_processes", "status", "String", 64, "'pending'"),
    ("approval_tasks", "status", "String", 64, "'open'"),
    ("attestation", "status", "String", 64, "'active'"),
    ("client_request_tickets", "status", "String", 64, "'open'"),
    ("edo_envelopes", "status", "String", 64, "'queued'"),
    ("inspection_prescription", "status", "String", 64, "'open'"),
    ("pack_run_items", "status", "String", 64, "'queued'"),
    ("pack_runs", "status", "String", 64, "'queued'"),
    ("package_preset_items", "output_format", "String", 64, "'both'"),
    ("package_preset_items", "replace_mode", "String", 64, "'none'"),
    ("package_presets_v2", "source_type", "String", 64, "'csv'"),
    ("package_presets_v2", "status", "String", 64, "'draft'"),
    ("package_profiles_v2", "status", "String", 64, "'draft'"),
    ("package_requirements", "status", "String", 64, "'missing'"),
    ("package_requirements", "type", "String", 64, "'file'"),
    ("package_runs", "status", "String", 64, "'draft'"),
    ("ppeitem", "category", "String", 64, "'other'"),
    ("training_session", "status", "String", 64, "'scheduled'"),
```
Leave the other 15 rows (`approval_instance_steps='PENDING'`, `approval_instances='DRAFT'`, `approval_route_steps='APPROVE'`, `equipment='ACTIVE'`, `idempotency_keys='PENDING'`, `incident.severity='MEDIUM'`, `incident.status='REPORTED'`, `npa='ACTIVE'`, `permit='ACTIVE'`, `pipeline_runs='QUEUED'`, `plantask='OPEN'`, `ppeissue='ISSUED'`, `template='DRAFT'`, `templateversion='UPLOADED'`, `tenant.kind='customer'`) exactly as-is.

- [ ] **Step 2: Run the iter38 pin tests + the parity audit test (app-free, SQLite/no-DB)**

PowerShell:
```powershell
$out = "$env:TEMP\pin_audit.txt"; if (Test-Path $out){Remove-Item $out}
& ".venv\Scripts\python.exe" -u -m pytest backend/tests/test_iter38_server_default_cohort.py backend/tests/test_audit_server_default_parity.py -p no:cacheprovider -q > $out 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $out -Tail 10
```
Expected: **PASS** (all). `test_audit_drift_total_count_is_zero` stays green because `server_default_parity._alter_column_target` credits parity on *presence* of a non-None `server_default`, not its value (verified in the audit source).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_iter38_server_default_cohort.py
git commit -m "test(migrations): sync iter38 _COHORT_C pin to corrected lowercase defaults

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Regression — app-free migration/enum cohort suite

- [ ] **Step 1: Run the related migration cohort tests (no DB, light imports)**

PowerShell:
```powershell
$out = "$env:TEMP\regress.txt"; if (Test-Path $out){Remove-Item $out}
& ".venv\Scripts\python.exe" -u -m pytest backend/tests/test_iter37_server_default_cohort.py backend/tests/test_iter38_server_default_cohort.py backend/tests/test_iter43_incident_status_enum_type_parity.py backend/tests/test_audit_server_default_parity.py backend/tests/test_docker_compose_run_migrations.py -p no:cacheprovider -q > $out 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $out -Tail 12
```
Expected: **PASS** (all). No commit (read-only verification). If anything fails, fix before proceeding.

---

## Task 5: Make the release docs reflect the real (now-fixed) blocker

**Files:**
- Modify: `KNOWN_LIMITATIONS.md` (CI-stabilization section — the `alembic-postgres-upgrade` bullet)
- Modify: `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (CI status note)

- [ ] **Step 1: Replace the stale `DuplicateObjectError` description** with a dated note: the original `DuplicateObjectError` was resolved (migration `8d2c1a6c5e24` uses `create_type=False`); the actual 2026-05-31 boot-blocker was `iter38` setting enum `server_default` to UPPER_CASE member names vs lowercase enum labels (`InvalidTextRepresentationError`), now fixed and guarded by `backend/tests/test_alembic_postgres_upgrade.py`. Note the fix is verified canonically on local PG16; CI 3.12.12 re-validation pending re-enable.

- [ ] **Step 2: Commit**

```bash
git add KNOWN_LIMITATIONS.md docs/stabilization/RELEASE_BLOCKERS_STATUS.md
git commit -m "docs(release): record iter38 enum server_default fix as the real PG boot-blocker

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Final canonical verification + cleanup

- [ ] **Step 1: One clean end-to-end canonical run on a fresh DB**

PowerShell:
```powershell
docker exec promtech-cabinet-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS alembic_verify;"
docker exec promtech-cabinet-db-1 psql -U postgres -c "CREATE DATABASE alembic_verify;"
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/alembic_verify"
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
$out = "$env:TEMP\final_upgrade.txt"; if (Test-Path $out){Remove-Item $out}
& ".venv\Scripts\python.exe" -u -m alembic -c backend/app/migrations/alembic.ini upgrade heads > $out 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $out -Tail 5
```
Expected: **EXIT=0**, last line an `INFO ... Running upgrade ... -> <final head>` with no traceback.

- [ ] **Step 2: Drop the throwaway DB**

```bash
docker exec promtech-cabinet-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS alembic_verify;"
```

- [ ] **Step 3: Update the handoff** in `AI_IMPLEMENTATION_REPORT.md` (top entry): real boot-blocker found via local PG16 reproduction (not the documented `DuplicateObjectError`), 18 iter38 defaults corrected, guard test added, canonical upgrade green locally; next = re-enable CI (W0) for 3.12.12 confirmation + RB-002/003/005 re-validation. Commit.

---

## Out of scope (follow-up plans once backend boots on PG)

RB-002 perf-baseline (branch `chore/rb-002-flow-scenarios-trim` exists), RB-003 final-acceptance regen, RB-005 e2e-smoke environmental diagnosis, coverage-floor bootstrap → `TZ-6.3-V11-01`, `container-image-scan` CVE (temp exception to 2026-08-31), and the latent **varchar** parity question (the 4 plain-varchar status columns keep UPPER_CASE defaults that may not match the ORM's persisted form — non-blocking since varchar accepts any string; flag if a downstream check cares).
