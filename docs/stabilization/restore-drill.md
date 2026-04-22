# Restore Drill (Stabilization)

_Last updated: 2026-04-22._

This document defines repeatable backup/restore drills with machine-readable evidence for stabilization sign-off.

## Restore drill gate (exact workflow + artifacts)

| Gate | Status | Partial/missing reason | Exact command/workflow | Artifact path(s) |
|---|---|---|---|---|
| Restore drill (sqlite + postgres-minio) | `partial` | Formal release go/no-go closure is still open in readiness tracking; evidence generation exists but checklist closure is still `NO` in `RELEASE_READINESS.md`. | Local commands: `python scripts/restore_drill.py --mode sqlite --output-dir artifacts/restore-drill` and `python scripts/restore_drill.py --mode postgres-minio --output-dir artifacts/restore-drill`; CI workflow: `.github/workflows/restore-drill.yml` (`restore-drill` job, scheduled Mondays 03:30 UTC + manual dispatch). | `artifacts/restore-drill/<mode>-<timestamp>.json`, `artifacts/restore-drill/latest-sqlite.json`, `artifacts/restore-drill/latest-postgres-minio.json`; uploaded artifact name: `restore-drill-evidence`. |

Release decision is governed by the **single go/no-go checklist** in `RELEASE_READINESS.md`.

## Scope and goal

The drill validates that we can:

1. Seed representative tenant data.
2. Perform database + object-storage backup.
3. Restore into a disposable environment.
4. Verify row counts + checksums + object integrity/metadata.
5. Execute application smoke check against restored environment.

## Drill modes

### 1) `--mode sqlite`

Local/disposable baseline mode:

- SQLite DB backup/restore.
- Filesystem object storage archive/restore.
- Health smoke using restored SQLite DB.

### 2) `--mode postgres-minio`

Provider-like mode for CI rehearsals:

- Postgres logical dump/restore (`pg_dump`/`pg_restore`).
- MinIO object backup archive + restore into separate restore bucket.
- Verification includes:
  - row counts,
  - document checksums,
  - object payload hash integrity,
  - object metadata and content-type checks,
  - app smoke on restored Postgres + restored MinIO bucket.

## Prerequisites

- Python 3.12+.
- Backend dependencies installed:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

- For `postgres-minio` mode:
  - Reachable Postgres source and restore databases.
  - Reachable MinIO endpoint and credentials.
  - `pg_dump` and `pg_restore` available in PATH.

## Commands

Run from repository root.

SQLite mode:

```bash
python scripts/restore_drill.py --mode sqlite --output-dir artifacts/restore-drill
```

Postgres/MinIO mode:

```bash
python scripts/restore_drill.py \
  --mode postgres-minio \
  --output-dir artifacts/restore-drill \
  --postgres-source-dsn postgresql://postgres:postgres@localhost:5432/restore_drill_source \
  --postgres-restore-dsn postgresql://postgres:postgres@localhost:5432/restore_drill_restore \
  --minio-endpoint localhost:9000 \
  --minio-access-key minioadmin \
  --minio-secret-key minioadmin
```

Optional flags:

- `--tenant-slug <slug>`: override seeded representative tenant slug.
- `--minio-source-bucket <name>` / `--minio-restore-bucket <name>`.
- Env aliases are supported via `RESTORE_DRILL_*` variables.

## Evidence output

Script writes mode-specific evidence:

- `artifacts/restore-drill/<mode>-<timestamp>.json` (immutable)
- `artifacts/restore-drill/latest-<mode>.json` (latest pointer)

Top-level JSON keys:

- `drill`: metadata including mode, duration, RTO/RPO assumptions.
- `seed`: seeded counts and object manifest.
- `backup`: backup artifact checksums.
- `restore.state`: restored state snapshot.
- `restore.verification`: boolean checks + mismatch list.
- `smoke_boot`: CLI health check command/result.
- `success`: aggregate pass/fail.

## Acceptance criteria

A drill run is **accepted** only when all conditions are true:

- `success == true`
- `restore.verification.counts_match == true`
- `restore.verification.documents_checksum_match == true`
- `restore.verification.object_content_and_metadata_match == true`
- `restore.verification.object_mismatches` is empty
- `smoke_boot.exit_code == 0`

Any failed condition is a **restore drill failure** and requires rollback/retry handling.

## RTO/RPO assumptions

Current encoded assumptions in evidence JSON:

- `assumed_rto_seconds = 900` (15 minutes)
- `assumed_rpo_seconds = 300` (5 minutes)

These are stabilization assumptions for rehearsal scoring only and are not production compliance guarantees.

## Explicit limitations

1. `postgres-minio` uses logical dump/restore, not managed provider snapshot primitives (e.g. RDS snapshot restore).
2. Drill environment is disposable CI/local infra; no production traffic or production encryption/KMS path is exercised.
3. No fault injection (corrupt WAL/snapshot, partial network partition, credential rotation during restore).
4. Smoke check is CLI health check; it is not a full route-level regression suite.
5. MinIO metadata validation is scoped to object user metadata + content-type for restored objects.

## Rollback note (on failed drill)

If drill fails in CI/staging rehearsal:

1. Mark run as failed and preserve uploaded evidence artifact.
2. Discard restore DB and restore bucket (do not reuse partially restored state).
3. Recreate clean restore targets and rerun drill after corrective action.
4. Link evidence diff in incident/task before re-enabling pass criteria gate.

## CI workflow

Workflow file: `.github/workflows/restore-drill.yml`.

- Trigger modes:
  - Weekly schedule (non-prod): Mondays at 03:30 UTC.
  - Manual trigger: `workflow_dispatch`.
- CI starts service containers for Postgres and MinIO.
- Published artifact: `restore-drill-evidence` from `artifacts/restore-drill/`.

## Cross-links

- Tenant restore operational sequence: `docs/runbooks/RESTORE_TENANT.md`
- Storage incident recovery context: `docs/runbooks/STORAGE_ISSUES.md`
- Broader operational guidance: `docs/OPERATIONS.md`
