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
- `go_no_go`: formal RTO/RPO decision (RC-012) — measured vs threshold + `decision`.
- `success`: aggregate pass/fail (integrity **and** `go_no_go.decision == "go"`).

## Acceptance criteria

A drill run is **accepted** only when all conditions are true:

- `success == true`
- `restore.verification.counts_match == true`
- `restore.verification.documents_checksum_match == true`
- `restore.verification.object_content_and_metadata_match == true`
- `restore.verification.object_mismatches` is empty
- `smoke_boot.exit_code == 0`
- `go_no_go.rto_met == true` — recovery completed within the RTO budget
- `go_no_go.rpo_met == true` — backup staleness within the RPO budget
- `go_no_go.decision == "go"`

Any failed condition is a **restore drill failure** and requires rollback/retry handling.

## RTO/RPO go/no-go (RC-012)

The drill now emits a formal go/no-go decision (`go_no_go` block), not just static
assumptions:

- **RTO (Recovery Time Objective)** — `rto_measured_seconds` is the wall-clock from
  "backup available" to "restored + verified + booted" (restore + verification + smoke).
  `rto_met = rto_measured_seconds <= rto_threshold_seconds`.
- **RPO (Recovery Point Objective)** — `rpo_measured_seconds` is the backup staleness
  vs the last write (the rehearsal's seed→backup lag; see `rpo_basis`).
  `rpo_met = rpo_measured_seconds <= rpo_threshold_seconds`.
- **`decision`** is `go` only when data-integrity checks pass **and** both objectives
  are met; otherwise `no-go`. This is folded into `success`.

Budgets (thresholds) default to the production targets from ТЗ vNext §31.6 —
**RTO ≤ 4h (`14400`s), RPO ≤ 24h (`86400`s)** — and are overridable:

```bash
python scripts/restore_drill.py --mode postgres-minio \
  --rto-threshold-seconds 14400 --rpo-threshold-seconds 86400
# or via env: RESTORE_DRILL_RTO_SECONDS / RESTORE_DRILL_RPO_SECONDS
```

The legacy `drill.assumed_rto_seconds` / `assumed_rpo_seconds` keys are retained for
back-compat and now mirror the configured thresholds; the authoritative go/no-go lives
in the `go_no_go` block.

**Caveat (honest scope):** the rehearsal seeds then immediately backs up, so the measured
RPO reflects this drill's own backup lag — a lower bound. **Production RPO is governed by
backup *cadence*, not by this drill**; `go_no_go.rpo_basis` states this in the evidence
so the number is never mistaken for a production guarantee.

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
