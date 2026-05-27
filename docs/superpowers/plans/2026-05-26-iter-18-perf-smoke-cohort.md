# iter-18 — RB-002e + RB-002f (perf-smoke cohort) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `perf-smoke` CI job green by closing two latent defects that surfaced after PR #584 unblocked api-1 startup: (RB-002e) the Alembic enum-creation race between `api`, `worker`, and `beat` containers, and (RB-002f) the missing admin bootstrap + login flow that causes 401s on `/api/v1/dashboard/summary`.

**Architecture:**
- RB-002e fix is configuration-only: restrict `alembic upgrade heads` to the `api` service via `RUN_MIGRATIONS` env var in `docker-compose.yml`. The entrypoint already honours this flag — only `api` should keep the default.
- RB-002f fix is two-part: (a) supply `ADMIN_BOOTSTRAP=1` + `ADMIN_PASSWORD` + `ADMIN_TENANT=demo` to the perf-smoke `.env` so `dev_bootstrap.bootstrap_admin_user` creates the admin user; (b) replace the bare `--path /api/v1/dashboard/summary` call with a `--flow-json` that first POSTs `/api/v1/auth/login` and captures the bearer token. `api_load.py` already supports `--flow-json` with `capture` — no script extension needed.

**Tech Stack:**
- Docker Compose v2 (services definition)
- GitHub Actions YAML (workflow steps + here-doc env injection)
- Python 3.12 + pytest (pin tests)
- PyYAML (for reading workflow file in pin tests — already in `requirements-dev.txt`)
- `httpx` async (already used by `scripts/perf/api_load.py`)

---

## File Structure

Files modified or created in this iter:

| Path | Action | Responsibility |
|---|---|---|
| `docker-compose.yml` | Modify | Add `RUN_MIGRATIONS=false` env to `worker` and `beat` services so only `api` runs `alembic upgrade heads`. |
| `.github/workflows/ci.yml` | Modify | Extend the `perf-smoke` job's "Fill required CI secrets" step with admin-bootstrap env vars; replace bare `/api/v1/dashboard/summary` call with a `--flow-json` invocation that authenticates first. |
| `scripts/perf/flows/dashboard_summary.json` | Create | Two-step flow definition consumed by `api_load.py --flow-json`: step 1 POST `/api/v1/auth/login` and capture `access_token`; step 2 GET `/api/v1/dashboard/summary` with `Authorization: Bearer {{access_token}}`. |
| `backend/tests/test_docker_compose_run_migrations.py` | Create | Pin test for RB-002e — asserts `worker` and `beat` services have `RUN_MIGRATIONS=false` in `docker-compose.yml` and `api` does not (default true preserved). |
| `backend/tests/test_perf_smoke_env_contract.py` | Create | Pin test for RB-002f — asserts the perf-smoke `.env` here-doc in `ci.yml` contains the four admin-bootstrap keys (`ADMIN_BOOTSTRAP`, `ADMIN_PASSWORD`, `ADMIN_TENANT`, `APP_ENV`). |
| `backend/tests/test_perf_smoke_dashboard_flow.py` | Create | Pin test for RB-002f part B — asserts `dashboard_summary.json` flow has exactly two steps with the expected method/path/capture shape. |

**Why this decomposition:**
- Three pin tests, each owning one invariant. Future edits to either `docker-compose.yml`, `ci.yml`, or the flow JSON cannot silently regress these fixes.
- The flow JSON lives at `scripts/perf/flows/` (new directory), keeping perf assets co-located with `scripts/perf/api_load.py`. The directory is a natural extension point for future endpoint flows (e.g. `templates_search.json`).
- No backend Python code changes — the entire fix is in CI/infra config plus pin tests. This keeps the PR diff focused.

---

## Task 1: RB-002e — restrict Alembic upgrade to `api` service

**Files:**
- Modify: `docker-compose.yml:102-141` (`worker` and `beat` service blocks)
- Create: `backend/tests/test_docker_compose_run_migrations.py`

### Background

The entrypoint at `scripts/docker-entrypoint.sh:4-6` runs:

```bash
if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  python -m alembic -c backend/app/migrations/alembic.ini upgrade heads
fi
```

All three services (`api`, `worker`, `beat`) inherit this entrypoint from the shared Dockerfile (`Dockerfile:44`). They all start nearly simultaneously and race on the `CREATE TYPE` DDL for PG enums in migration `8d2c1a6c5e24_domain_normalization.py:43-66`. Result: `duplicate key value violates unique constraint "pg_type_typname_nsp_index"` on the second container to arrive at enum creation.

The fix is to set `RUN_MIGRATIONS=false` on `worker` and `beat`, leaving `api` as the sole migration runner.

- [ ] **Step 1: Write the failing pin test**

Create `backend/tests/test_docker_compose_run_migrations.py`:

```python
"""Pin test for RB-002e — only `api` service should run alembic upgrade."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose_config() -> dict:
    with COMPOSE_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _env_map(service: dict) -> dict[str, str]:
    """Normalize compose `environment` (list or dict) into a dict."""
    env = service.get("environment", {})
    if isinstance(env, list):
        return dict(item.split("=", 1) for item in env if "=" in item)
    return {str(k): str(v) for k, v in env.items()}


def test_api_service_does_not_disable_migrations(compose_config: dict) -> None:
    """`api` MUST keep the entrypoint default (RUN_MIGRATIONS=true)."""
    api_env = _env_map(compose_config["services"]["api"])
    assert api_env.get("RUN_MIGRATIONS", "true") == "true", (
        "api service must run migrations — leave RUN_MIGRATIONS unset or 'true'"
    )


def test_worker_service_disables_migrations(compose_config: dict) -> None:
    """`worker` MUST NOT run migrations (RB-002e race fix)."""
    worker_env = _env_map(compose_config["services"]["worker"])
    assert worker_env.get("RUN_MIGRATIONS") == "false", (
        "worker service must set RUN_MIGRATIONS=false to avoid alembic race with api"
    )


def test_beat_service_disables_migrations(compose_config: dict) -> None:
    """`beat` MUST NOT run migrations (RB-002e race fix)."""
    beat_env = _env_map(compose_config["services"]["beat"])
    assert beat_env.get("RUN_MIGRATIONS") == "false", (
        "beat service must set RUN_MIGRATIONS=false to avoid alembic race with api"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_docker_compose_run_migrations.py -v`

Expected: 2 of 3 tests FAIL with `assert None == 'false'` for `test_worker_service_disables_migrations` and `test_beat_service_disables_migrations`. `test_api_service_does_not_disable_migrations` passes (default is "true").

- [ ] **Step 3: Edit `docker-compose.yml` to add `RUN_MIGRATIONS=false` to worker and beat**

In `docker-compose.yml`, locate the `worker` service block (lines 102-127) and the `beat` service block (lines 129-141). Add the env var to each.

For `worker` (after `restart: unless-stopped`, alongside `env_file`):

```yaml
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - .env
    environment:
      # RB-002e: only `api` runs `alembic upgrade heads`; worker/beat must skip to avoid
      # the CREATE TYPE race on PG enums in migration 8d2c1a6c5e24.
      RUN_MIGRATIONS: "false"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
    command:
      [
        "celery",
        "-A",
        "app.services.celery_app.celery_app",
        "worker",
        "-Q",
        "default,pdf",
        "-l",
        "info",
      ]
```

For `beat`:

```yaml
  beat:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - .env
    environment:
      RUN_MIGRATIONS: "false"  # RB-002e — see worker comment
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: ["celery", "-A", "app.services.celery_app.celery_app", "beat", "-l", "info"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_docker_compose_run_migrations.py -v`

Expected: 3 of 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml backend/tests/test_docker_compose_run_migrations.py
git commit -m "$(cat <<'EOF'
fix(compose): iter-18 RB-002e — restrict alembic upgrade to api service

worker and beat containers inherit the same Dockerfile entrypoint as api,
which runs `alembic upgrade heads` when RUN_MIGRATIONS=true (default). All
three start simultaneously and race on CREATE TYPE for PG enums introduced
by migration 8d2c1a6c5e24_domain_normalization.py, producing
"duplicate key value violates unique constraint pg_type_typname_nsp_index"
on the second container.

Fix: set RUN_MIGRATIONS=false explicitly on worker and beat in
docker-compose.yml. api keeps the default ("true") and remains the sole
migration runner.

Pin test backend/tests/test_docker_compose_run_migrations.py asserts the
invariant going forward.

Closes: RB-002e
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: RB-002f part A — supply admin bootstrap env vars to perf-smoke

**Files:**
- Modify: `.github/workflows/ci.yml:466-476` (perf-smoke "Fill required CI secrets" step)
- Create: `backend/tests/test_perf_smoke_env_contract.py`

### Background

`backend/app/services/dev_bootstrap.py:48-58` defines `bootstrap_admin_user`:

```python
async def bootstrap_admin_user(settings: Settings) -> None:
    if not settings.admin_bootstrap:
        return
    if settings.app_env not in {"development", "test"}:
        logger.warning("admin.bootstrap.skipped", extra={"reason": "not-dev", ...})
        return
    if not settings.admin_password.strip():
        logger.warning("admin.bootstrap.skipped", extra={"reason": "empty-password"})
        return
    ...  # creates admin user
```

Settings defaults from `backend/app/core/config.py:311-314`:

```python
admin_bootstrap: bool = Field(False, alias="ADMIN_BOOTSTRAP")
admin_email: str = Field("admin@example.com", alias="ADMIN_EMAIL")
admin_password: str = Field("", alias="ADMIN_PASSWORD")
admin_tenant: str = Field("public", alias="ADMIN_TENANT")
```

`app_env` defaults to `"development"` (`config.py:258`), so that branch is satisfied. The perf-smoke job's `.env` here-doc at `ci.yml:470-476` does not set any of the admin vars, so bootstrap returns early with `empty-password` and no admin user is ever created. Subsequent perf-smoke calls to `/api/v1/dashboard/summary` therefore receive 401.

Fix: add `ADMIN_BOOTSTRAP=1`, `ADMIN_PASSWORD=<ci-only>`, `ADMIN_TENANT=demo`, and `APP_ENV=development` to the here-doc.

- [ ] **Step 1: Write the failing pin test**

Create `backend/tests/test_perf_smoke_env_contract.py`:

```python
"""Pin test for RB-002f — perf-smoke ci.yml must seed admin-bootstrap env vars."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CI_YAML = ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_KEYS = (
    "ADMIN_BOOTSTRAP",
    "ADMIN_PASSWORD",
    "ADMIN_TENANT",
    "APP_ENV",
)


@pytest.fixture(scope="module")
def perf_smoke_env_block() -> str:
    """Extract the perf-smoke `Fill required CI secrets` here-doc content."""
    text = CI_YAML.read_text(encoding="utf-8")
    # Find the perf-smoke job, then the env here-doc inside it.
    perf_smoke_idx = text.find("\n  perf-smoke:")
    assert perf_smoke_idx != -1, "perf-smoke job not found in ci.yml"
    perf_smoke_block = text[perf_smoke_idx:]
    match = re.search(
        r"cat >> \.env <<'EOF'(.*?)EOF",
        perf_smoke_block,
        re.DOTALL,
    )
    assert match is not None, (
        "perf-smoke `cat >> .env <<'EOF' ... EOF` block not found"
    )
    return match.group(1)


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_perf_smoke_env_contains_admin_bootstrap_key(
    key: str, perf_smoke_env_block: str
) -> None:
    """Each required key must appear with a non-empty RHS in the here-doc."""
    pattern = rf"^\s*{re.escape(key)}=\S+"
    assert re.search(pattern, perf_smoke_env_block, re.MULTILINE), (
        f"perf-smoke env block must set {key}=<non-empty>; "
        "see RB-002f, dev_bootstrap.bootstrap_admin_user skip conditions."
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_perf_smoke_env_contract.py -v`

Expected: 4 of 4 parametrized tests FAIL — none of `ADMIN_BOOTSTRAP`, `ADMIN_PASSWORD`, `ADMIN_TENANT`, `APP_ENV` are in the current env block.

- [ ] **Step 3: Edit `ci.yml` to extend the here-doc**

Locate `.github/workflows/ci.yml:466-476` (the "Fill required CI secrets" step inside `perf-smoke`). Append four lines to the here-doc:

```yaml
      - name: Fill required CI secrets (placeholders only)
        # Staging-hardening (backend/app/core/config.py::bootstrap) rejects empty
        # SECRET_KEY / S3_ACCESS_KEY / S3_SECRET_KEY. .env.example ships them
        # blank by design — fill with CI-only placeholders so API can boot.
        # RB-002f: also seed admin-bootstrap env so dev_bootstrap creates the
        # demo admin user; otherwise perf-smoke calls to /api/v1/dashboard/summary
        # 401 because there is no user/token to authenticate.
        run: |
          cat >> .env <<'EOF'
          SECRET_KEY=ci-perf-smoke-not-for-production
          POSTGRES_PASSWORD=ptd
          S3_ACCESS_KEY=minioadmin
          S3_SECRET_KEY=minioadmin
          APP_ENV=development
          ADMIN_BOOTSTRAP=1
          ADMIN_PASSWORD=PerfSmokeAdmin123!
          ADMIN_TENANT=demo
          EOF
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_perf_smoke_env_contract.py -v`

Expected: 4 of 4 parametrized tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml backend/tests/test_perf_smoke_env_contract.py
git commit -m "$(cat <<'EOF'
ci(perf-smoke): iter-18 RB-002f-A — seed admin-bootstrap env vars

backend/app/services/dev_bootstrap.py:48-58 skips admin user creation when
ADMIN_PASSWORD is empty (logs admin.bootstrap.skipped reason=empty-password).
The perf-smoke job's existing `Fill required CI secrets` step only set
SECRET_KEY / POSTGRES_PASSWORD / S3 credentials, so no admin user was ever
created and every /api/v1/dashboard/summary call returned 401.

Fix: extend the here-doc with APP_ENV=development, ADMIN_BOOTSTRAP=1,
ADMIN_PASSWORD=PerfSmokeAdmin123!, ADMIN_TENANT=demo so
dev_bootstrap.bootstrap_admin_user creates the demo admin during startup.

Pin test backend/tests/test_perf_smoke_env_contract.py asserts all four
keys remain in the here-doc.

Part of RB-002f closure (auth flow added in next commit).
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: RB-002f part B — add login flow for `/api/v1/dashboard/summary`

**Files:**
- Create: `scripts/perf/flows/dashboard_summary.json`
- Modify: `.github/workflows/ci.yml:512-523` (dashboard summary perf step)
- Create: `backend/tests/test_perf_smoke_dashboard_flow.py`

### Background

`scripts/perf/api_load.py` does NOT have a `--login` argument — searched with `grep -i 'login|token|bearer|auth|--admin|--password'` returns zero hits. But it does have `--flow-json`, which supports multi-step flows with `capture` (lines 98-142). A `flow-json` value containing two steps — POST login that captures `access_token`, GET dashboard that uses `Authorization: Bearer {{access_token}}` — fixes the auth gap without modifying `api_load.py`.

Login endpoint: `POST /api/v1/auth/login` accepts `{email, password}` per `LoginRequest` in `backend/app/api/routes/auth.py`. Response body shape is checked when writing the flow JSON.

- [ ] **Step 1: Confirm login response body shape**

Read the auth route to learn the response key for the bearer token.

Run: `python -c "import re; t=open('backend/app/api/routes/auth.py','r',encoding='utf-8').read(); print([m.group(0) for m in re.finditer(r'access_token|TokenResponse|class\s+Token\w+|token_type', t)])"`

Expected: prints occurrences of `access_token` and the response model name. Note the JSON path to the token (typically `access_token` at top-level — confirm before writing the flow). If the field is nested (e.g. `data.access_token`), adjust the `capture` key in Step 2.

- [ ] **Step 2: Create the flow JSON**

Create `scripts/perf/flows/dashboard_summary.json` (use the path confirmed in Step 1; the example below assumes top-level `access_token`):

```json
[
  {
    "method": "POST",
    "path": "/api/v1/auth/login",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "email": "admin@example.com",
      "password": "PerfSmokeAdmin123!"
    },
    "expect_status": 200,
    "capture": {
      "access_token": "access_token"
    }
  },
  {
    "method": "GET",
    "path": "/api/v1/dashboard/summary",
    "headers": {
      "Authorization": "Bearer {{access_token}}"
    },
    "expect_status": 200
  }
]
```

The flow runner (`api_load.py:_hit_flow`, lines 98-142) renders `{{access_token}}` from the capture context produced by step 0. The `X-Tenant: demo` header is set automatically by `api_load.py` from the CLI `--tenant demo` argument (see line 126).

Note: password `PerfSmokeAdmin123!` MUST match what was added to the `.env` here-doc in Task 2 Step 3. If you change one, change the other.

- [ ] **Step 3: Write the failing pin test**

Create `backend/tests/test_perf_smoke_dashboard_flow.py`:

```python
"""Pin test for RB-002f-B — perf-smoke dashboard flow has login + summary steps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLOW_FILE = ROOT / "scripts" / "perf" / "flows" / "dashboard_summary.json"


@pytest.fixture(scope="module")
def flow() -> list[dict]:
    return json.loads(FLOW_FILE.read_text(encoding="utf-8"))


def test_flow_has_exactly_two_steps(flow: list[dict]) -> None:
    assert len(flow) == 2, f"expected exactly 2 steps (login + summary), got {len(flow)}"


def test_step_0_is_auth_login_post(flow: list[dict]) -> None:
    step = flow[0]
    assert step["method"].upper() == "POST"
    assert step["path"] == "/api/v1/auth/login"
    assert step.get("expect_status", 200) == 200
    body = step.get("body", {})
    assert "email" in body and "password" in body, (
        "login step must POST email+password"
    )


def test_step_0_captures_access_token(flow: list[dict]) -> None:
    capture = flow[0].get("capture", {})
    assert "access_token" in capture, (
        "step 0 must capture the bearer token under key 'access_token'"
    )


def test_step_1_is_dashboard_summary_with_bearer(flow: list[dict]) -> None:
    step = flow[1]
    assert step["method"].upper() == "GET"
    assert step["path"] == "/api/v1/dashboard/summary"
    auth_header = step.get("headers", {}).get("Authorization", "")
    assert auth_header == "Bearer {{access_token}}", (
        "step 1 must use the captured token in the Authorization header"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_perf_smoke_dashboard_flow.py -v`

Expected: 4 of 4 tests PASS (because Step 2 already created the flow JSON with the right shape).

- [ ] **Step 5: Modify `ci.yml` to use the flow**

Locate `.github/workflows/ci.yml:512-523` (the second `python scripts/perf/api_load.py` invocation, which hits `/api/v1/dashboard/summary`). Replace the `--path /api/v1/dashboard/summary` argument with `--flow-json "$(cat scripts/perf/flows/dashboard_summary.json)"`.

The full replacement block (lines 512-523):

```yaml
          python scripts/perf/api_load.py \
            --base-url http://localhost:8000 \
            --flow-json "$(cat scripts/perf/flows/dashboard_summary.json)" \
            --tenant demo \
            --requests 60 \
            --concurrency 12 \
            --expect-status 200 \
            --max-error-rate 0.02 \
            --min-throughput 15 \
            --max-p95-ms 600 \
            --max-p99-ms 1200 \
            --output-json artifacts/perf/dashboard-smoke.json
```

Note: `--path` is removed (the flow defines paths internally). All other args (concurrency, thresholds, output) stay identical so the artifact schema does not change.

- [ ] **Step 6: Commit**

```bash
git add scripts/perf/flows/dashboard_summary.json .github/workflows/ci.yml backend/tests/test_perf_smoke_dashboard_flow.py
git commit -m "$(cat <<'EOF'
ci(perf-smoke): iter-18 RB-002f-B — login flow before /api/v1/dashboard/summary

scripts/perf/api_load.py has no --login argument and the dashboard endpoint
requires auth. The bare GET call from previous ci.yml returned 401 even
after the admin user existed (Task 2). api_load.py already supports
--flow-json with capture, so we use that instead of extending the script.

Adds scripts/perf/flows/dashboard_summary.json with two steps:
  1. POST /api/v1/auth/login {email, password} -> capture access_token
  2. GET /api/v1/dashboard/summary with Authorization: Bearer {{access_token}}

ci.yml dashboard probe switched from --path to --flow-json. All other
thresholds preserved so the artifact schema stays stable.

Pin test backend/tests/test_perf_smoke_dashboard_flow.py asserts the flow
shape (2 steps, login captures access_token, summary uses bearer).

Closes: RB-002f (combined with Task 2 env-var seeding).
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Verify CI run on the PR

**Files:** none

This is the only authoritative verification. Per `[[local-env-drift-windows]]` memory, the local Windows + Python 3.13 environment cannot run the full Docker stack reliably; CI on `ubuntu-latest` + Python 3.12.12 is the source of truth. Local pytest covers the pin tests only — the actual race + auth fix has to be validated in CI.

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin fix/iter-18-rb-002ef-perf-smoke-cohort
gh pr create --title "fix(ci): iter-18 RB-002e+f — perf-smoke cohort closure" --body "$(cat <<'EOF'
## Summary

Closes RB-002e and RB-002f by addressing two latent defects that surfaced after PR #584 unblocked api-1 startup:

- **RB-002e:** restrict `alembic upgrade heads` to the `api` service so `worker` and `beat` do not race on `CREATE TYPE`.
- **RB-002f-A:** seed admin-bootstrap env vars (`APP_ENV`, `ADMIN_BOOTSTRAP`, `ADMIN_PASSWORD`, `ADMIN_TENANT`) into the perf-smoke `.env` so `dev_bootstrap.bootstrap_admin_user` creates the demo admin.
- **RB-002f-B:** replace the bare `/api/v1/dashboard/summary` perf call with a `--flow-json` that first POSTs `/api/v1/auth/login` and captures the bearer token.

Spec: `docs/superpowers/specs/2026-05-26-mvp-closure-design.md` §3 iter-18.

## Test plan

- [ ] CI `alembic-postgres-upgrade` job green (race no longer reproduces with worker/beat skipping migration)
- [ ] CI `perf-smoke` job green (admin bootstrap succeeds, login flow gets 200, dashboard returns 200)
- [ ] Pin tests in `backend/tests/test_docker_compose_run_migrations.py`, `backend/tests/test_perf_smoke_env_contract.py`, `backend/tests/test_perf_smoke_dashboard_flow.py` all PASS
- [ ] Existing CI jobs (`backend-tests`, `smoke-compose`, etc.) stay green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Watch CI**

Wait for CI on the PR. Two jobs must specifically turn green: `alembic-postgres-upgrade` and `perf-smoke`. Use:

```bash
gh pr checks --watch
```

Expected: all jobs PASS. If `perf-smoke` log shows `admin.bootstrap.skipped` still — re-read Task 2 Step 3; the `.env` here-doc may have been mis-edited (indentation matters for here-docs). If it shows `401` on dashboard — re-read Task 3 Step 1 to confirm the JSON path for the token capture.

- [ ] **Step 3: If a new latent issue surfaces (RB-002g)**

Per spec §4 Risk #2, this is an expected mode. Investigate the failure, write a follow-up plan `docs/superpowers/plans/2026-05-26-iter-18.5-rb-002g.md`, do NOT block merge of this PR on that — unless the new issue means `perf-smoke` is still red, in which case open a sub-PR onto this branch and stack.

- [ ] **Step 4: Merge after approval**

```bash
gh pr merge --squash --delete-branch
```

This advances `main` and unblocks iter-21 (workflow dispatch) for RB-002 closure.

---

## Local execution notes

- **Python version:** the pin tests use `pyyaml` (already a transitive dep) and stdlib `re` / `json`. They run on either Python 3.12 (canonical) or 3.13 (local Windows fallback).
- **Running tests:** if `python3.12` is on PATH use it; otherwise `python -m pytest` per `CLAUDE.md`. Mismatched version is acceptable for these pin tests because they read static files only.
- **Cannot test the race locally:** the duplicate-key race is timing-dependent and Postgres-specific. Even running the full `docker-compose up` locally may not reproduce it reliably. Trust CI.
- **Token capture path:** if Task 3 Step 1 reveals the token lives at a path other than `access_token` (e.g. `tokens.access_token`), update the JSON `capture` value to that path. `_extract_json_path` in `api_load.py:60-72` walks dotted paths.

---

## Cross-references

- Spec: `docs/superpowers/specs/2026-05-26-mvp-closure-design.md` §3 iter-18
- Cohort knowledge: `[[rb002-enum-migration-cohort]]` memory entry
- App-level defects: `[[app-level-defects-post-billing]]` memory entry
- Predecessor PRs: [#581](https://github.com/aiprocadm/prt_ot_doc/pull/581) (RB-002 part 1), [#582](https://github.com/aiprocadm/prt_ot_doc/pull/582) (RB-002b), [#583](https://github.com/aiprocadm/prt_ot_doc/pull/583) (RB-002c), [#584](https://github.com/aiprocadm/prt_ot_doc/pull/584) (RB-002d)
- Entrypoint source: `scripts/docker-entrypoint.sh:4-6`
- Bootstrap skip logic: `backend/app/services/dev_bootstrap.py:48-58`
- Settings defaults: `backend/app/core/config.py:311-314` (admin_*), `:258-259` (app_env)
- Perf script: `scripts/perf/api_load.py` (`_hit_flow` at lines 98-142 for `--flow-json` semantics)
