# Restore Drill (Stabilization)

_Last updated: 2026-04-19._

This drill converts existing backup/restore tooling into a repeatable, evidence-backed stabilization check.

## Existing implementation evidence

- CLI operations exist in `backend/app/cli/main.py`:
  - `backup` command (queued operation payload).
  - `restore` command (queued operation payload).
- CLI behavior is covered in `tests/test_cli_commands.py`.
- Tenant restore runbook exists at `docs/runbooks/RESTORE_TENANT.md`.

## Drill objective

Validate that backup/restore workflow can be executed and audited without tenant-scope violations, with explicit artifacts captured for release readiness.

## Drill procedure (current executable steps)

1. **Record baseline context**
   - Capture git SHA and environment name used for the drill.
2. **Trigger backup operation**
   - Run: `python -m backend.app.cli.main backup --triggered-by stabilization-drill --json`
   - Save stdout JSON artifact.
3. **Trigger restore operation (test mode)**
   - Run: `python -m backend.app.cli.main restore --mode test --json`
   - Save stdout JSON artifact.
4. **Run post-restore isolation checks**
   - Run targeted suites:
     - `pytest tests/integration/test_tenant_isolation.py`
     - `pytest tests/integration/test_cross_tenant_resource_matrix.py`
5. **Run smoke health checks**
   - Use `scripts/smoke.sh` or `make smoke` path used by `.github/workflows/ci.yml` compose smoke job, depending on environment capabilities.

## Required evidence artifacts

- CLI JSON output for backup and restore command executions.
- Test reports for post-restore tenant isolation checks.
- Any smoke logs collected from the deployment target.

## Explicit current gaps

- `backend/app/cli/main.py` emits queued operation records; it does not itself perform infrastructure snapshot/restore.
- `docs/runbooks/RESTORE_TENANT.md` is high-level and does not prescribe artifact naming or retention windows.
- No dedicated CI workflow currently executes this drill end-to-end on a schedule.

## Acceptance criteria for this workstream

- Drill is reproducible from this document using only existing scripts/commands.
- Every execution produces an evidence bundle (CLI outputs + test logs + smoke result).
- Any failed tenant-isolation check blocks stabilization sign-off.
