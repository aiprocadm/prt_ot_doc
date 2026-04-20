# Restore Drill (Stabilization)

_Last updated: 2026-04-19._

This document defines a repeatable backup/restore drill with machine-readable evidence for stabilization sign-off.

## Scope and goal

The drill validates that we can:

1. Seed representative tenant data.
2. Perform database + object-storage backup.
3. Restore into a disposable environment.
4. Verify DB counts/checksums + object metadata/content integrity.
5. Execute an application smoke boot check against the restored DB.

## Prerequisites

- Python 3.12+.
- Backend dependencies installed:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

- Local shell environment that can run subprocess commands.

> The current scripted drill uses disposable local SQLite + filesystem object storage to avoid production coupling. In CI this is still a non-prod environment.

## Command

Run from repository root:

```bash
python scripts/restore_drill.py --output-dir artifacts/restore-drill
```

Optional flags:

- `--tenant-slug <slug>`: override the seeded representative tenant slug.
- `--output-dir <path>`: move evidence output location (default is `artifacts/restore-drill`).

## Evidence output

The script writes:

- `artifacts/restore-drill/<timestamp>.json` (immutable per run)
- `artifacts/restore-drill/latest.json` (latest pointer)

Top-level JSON keys:

- `drill`: run metadata, duration, RTO/RPO assumptions.
- `seed`: seeded counts and object manifest.
- `backup`: backup artifact checksums.
- `restore.state`: restored state snapshot.
- `restore.verification`: boolean checks + mismatch list.
- `smoke_boot`: CLI health check command/result.
- `success`: aggregate pass/fail.

## Evidence interpretation

Treat drill run as **pass** only when all are true:

- `success == true`
- `restore.verification.counts_match == true`
- `restore.verification.documents_checksum_match == true`
- `restore.verification.object_content_and_metadata_match == true`
- `smoke_boot.exit_code == 0`

Treat run as **fail** if any condition above is false or if `object_mismatches` is non-empty.

## CI/manual workflow

Workflow file: `.github/workflows/restore-drill.yml`.

- Trigger modes:
  - Weekly schedule (non-prod): Mondays at 03:30 UTC.
  - Manual trigger: `workflow_dispatch`.
- Published artifact: `restore-drill-evidence` upload of `artifacts/restore-drill/`.

## RTO/RPO assumptions (current)

The current drill encodes assumptions in evidence JSON:

- `assumed_rto_seconds = 900` (15 minutes)
- `assumed_rpo_seconds = 300` (5 minutes)

These are stabilization assumptions for drill scoring and must be revisited before production compliance sign-off.

## Unresolved risks

1. The drill currently validates a representative local backup/restore path, not provider-native snapshots (e.g., managed Postgres snapshots, S3 versioned restore).
2. No chaos/fault injection is included (partial object loss, checksum corruption mid-restore, WAL gap simulation).
3. Smoke verification is limited to CLI health boot and does not yet include full HTTP route smoke against a restored deployment.
4. No automatic alerting/escalation integration yet (artifact is uploaded but not policy-gated in CI).

## Cross-links to operational runbooks

- Tenant restore operational sequence: `docs/runbooks/RESTORE_TENANT.md`
- Storage incident recovery context: `docs/runbooks/STORAGE_ISSUES.md`
- Broader operational guidance: `docs/OPERATIONS.md`

Use this drill evidence as input for those runbooks when planning staging/prod restore rehearsals.
